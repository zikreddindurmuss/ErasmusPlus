#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  v1.5 AKILLI VERİ İŞLEME HATTI (Smart Data Pipeline)       ║
║  Otonom Erasmus Yapay Zeka Mentorluk Projesi                ║
╚══════════════════════════════════════════════════════════════╝

Özellikler:
  • Hibrit belge okuma (pdfplumber + pypdf fallback + docx2txt)
  • Tablo çıkarma → Markdown dönüşümü
  • Opsiyonel OCR (pytesseract + pdf2image — yüklüyse devreye girer)
  • Qwen 2.5 (Ollama) ile yerel LLM metin temizleme
  • Artımlı indeksleme (MD5 hash ile değişiklik takibi)
  • Chunk caching (yeniden inşada Qwen'i tekrar çağırmaz)
  • OpenAI embedding + FAISS vektör veritabanı

Kullanım:
  python build_db.py              # Normal çalıştırma (artımlı)
  python build_db.py --rebuild    # Sıfırdan tam yeniden inşa
  python build_db.py --no-llm     # Qwen temizleme olmadan
"""

import os
import sys
import json
import hashlib
import time
import argparse
from pathlib import Path
from datetime import datetime

# Windows terminal UTF-8 encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# PDF & Document
import pypdf
import pdfplumber
import docx2txt

# LangChain & AI
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Ollama — pipeline başlatılırken dinamik yüklenir
OllamaLLM = None

# Opsiyonel OCR
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ═════════════════════════════════════════════════════════════
#  KONFİGÜRASYON
# ═════════════════════════════════════════════════════════════
load_dotenv()

INPUT_DIR = Path("./info_bank")
OUTPUT_DIR = Path("./faiss_index")
HASH_FILE = Path("./processed_files.json")
CACHE_DIR = Path("./.chunk_cache")

OLLAMA_MODEL = "qwen2.5:3b"
EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY bulunamadı! .env dosyasını kontrol edin.")
    sys.exit(1)


# ═════════════════════════════════════════════════════════════
#  YARDIMCI: Renkli Terminal Çıktısı
# ═════════════════════════════════════════════════════════════
class Log:
    """Renkli ve yapılandırılmış terminal çıktıları."""

    # Windows terminal ANSI desteğini etkinleştir
    if sys.platform == "win32":
        os.system("")  # Windows 10+ ANSI escape aktifleştirme
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    _C = "\033[96m"   # Cyan
    _G = "\033[92m"   # Green
    _Y = "\033[93m"   # Yellow
    _R = "\033[91m"   # Red
    _B = "\033[1m"    # Bold
    _E = "\033[0m"    # Reset

    @staticmethod
    def banner():
        print(f"""{Log._C}{Log._B}
+==============================================================+
|  [*] v1.5 AKILLI VERI ISLEME HATTI                           |
|      Otonom Erasmus AI Mentorluk Projesi                     |
+==============================================================+{Log._E}""")

    @staticmethod
    def step(num, msg):
        print(f"\n{Log._B}[Aşama {num}/6]{Log._E} {Log._C}{msg}{Log._E}")

    @staticmethod
    def ok(msg):
        print(f"  {Log._G}[OK]{Log._E} {msg}")

    @staticmethod
    def warn(msg):
        print(f"  {Log._Y}[!]{Log._E} {msg}")

    @staticmethod
    def err(msg):
        print(f"  {Log._R}[X]{Log._E} {msg}")

    @staticmethod
    def progress(cur, total, name=""):
        bar_len = 30
        filled = int(bar_len * cur / total) if total else 0
        bar = "#" * filled + "-" * (bar_len - filled)
        pct = (cur / total * 100) if total else 0
        label = name[:45] if name else ""
        print(f"\r  [{bar}] {pct:5.1f}% ({cur}/{total}) {label}", end="", flush=True)
        if cur >= total:
            print()


# ═════════════════════════════════════════════════════════════
#  ARTIMLI İNDEKSLEME: MD5 Dosya Takipçisi
# ═════════════════════════════════════════════════════════════
class FileTracker:
    """processed_files.json ile dosya değişikliklerini izler."""

    def __init__(self, hash_file: Path):
        self.hash_file = hash_file
        self.records: dict = self._load()

    # ---- I/O ----
    def _load(self) -> dict:
        if self.hash_file.exists():
            try:
                with open(self.hash_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save(self):
        with open(self.hash_file, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    # ---- Hash ----
    @staticmethod
    def md5(filepath: Path) -> str:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()

    # ---- Sınıflandırma ----
    def classify(self, files: list[Path]) -> dict:
        """Dosyaları new / changed / unchanged / deleted olarak ayırır."""
        result = {"new": [], "changed": [], "unchanged": [], "deleted": []}
        current_keys = set()

        for fp in files:
            key = fp.name  # Dosya adını anahtar olarak kullan
            current_keys.add(key)
            digest = self.md5(fp)

            if key not in self.records:
                result["new"].append((fp, digest))
            elif self.records[key]["md5"] != digest:
                result["changed"].append((fp, digest))
            else:
                result["unchanged"].append((fp, digest))

        for key in list(self.records.keys()):
            if key not in current_keys:
                result["deleted"].append(key)

        return result

    def update(self, filepath: Path, digest: str, chunk_count: int):
        self.records[filepath.name] = {
            "md5": digest,
            "chunk_count": chunk_count,
            "processed_at": datetime.now().isoformat(),
        }

    def remove(self, key: str):
        self.records.pop(key, None)


# ═════════════════════════════════════════════════════════════
#  BELGE ÇIKARMA: PDF / DOCX
# ═════════════════════════════════════════════════════════════
def _table_to_markdown(table: list[list]) -> str:
    """Ham pdfplumber tablo → Markdown tablo."""
    if not table or not table[0]:
        return ""
    cleaned = []
    for row in table:
        cleaned.append([str(c).replace("\n", " ").strip() if c else "" for c in row])

    col_count = len(cleaned[0])
    lines = ["| " + " | ".join(cleaned[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in cleaned[1:]:
        while len(row) < col_count:
            row.append("")
        lines.append("| " + " | ".join(row[:col_count]) + " |")
    return "\n".join(lines)


def extract_pdf(filepath: Path) -> list[dict]:
    """PDF → sayfa listesi [{text, metadata}, ...]"""
    pages = []
    try:
        with pdfplumber.open(filepath) as pdf:
            total = len(pdf.pages)
            for idx, page in enumerate(pdf.pages):
                parts: list[str] = []

                # Tablo çıkarma
                tables = page.extract_tables()
                if tables:
                    for tbl in tables:
                        if tbl and any(any(c for c in row) for row in tbl):
                            parts.append(_table_to_markdown(tbl))

                # Metin çıkarma
                txt = page.extract_text() or ""
                if txt.strip():
                    parts.append(txt.strip())

                # OCR fallback (taranmış sayfalar)
                if not parts and OCR_AVAILABLE:
                    try:
                        imgs = convert_from_path(
                            str(filepath), first_page=idx + 1, last_page=idx + 1
                        )
                        for img in imgs:
                            ocr = pytesseract.image_to_string(img, lang="tur+spa+eng")
                            if ocr.strip():
                                parts.append(ocr.strip())
                    except Exception:
                        pass

                if parts:
                    pages.append({
                        "text": "\n\n".join(parts),
                        "metadata": {
                            "source": filepath.name,
                            "page": idx + 1,
                            "total_pages": total,
                            "has_tables": bool(tables),
                        },
                    })
    except Exception as e:
        Log.warn(f"pdfplumber hatası ({filepath.name}): {e} → pypdf fallback")
        try:
            reader = pypdf.PdfReader(str(filepath))
            for idx, pg in enumerate(reader.pages):
                txt = pg.extract_text() or ""
                if txt.strip():
                    pages.append({
                        "text": txt.strip(),
                        "metadata": {
                            "source": filepath.name,
                            "page": idx + 1,
                            "total_pages": len(reader.pages),
                            "has_tables": False,
                        },
                    })
        except Exception as e2:
            Log.err(f"pypdf de başarısız ({filepath.name}): {e2}")
    return pages


def extract_docx(filepath: Path) -> list[dict]:
    """DOCX → sayfa listesi."""
    try:
        text = docx2txt.process(str(filepath))
        if text and text.strip():
            return [{
                "text": text.strip(),
                "metadata": {
                    "source": filepath.name,
                    "page": 1,
                    "total_pages": 1,
                    "has_tables": False,
                },
            }]
    except Exception as e:
        Log.err(f"DOCX okuma hatası ({filepath.name}): {e}")
    return []


def extract_txt(filepath: Path) -> list[dict]:
    """TXT → sayfa listesi."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        if text and text.strip():
            return [{
                "text": text.strip(),
                "metadata": {
                    "source": filepath.name,
                    "page": 1,
                    "total_pages": 1,
                    "has_tables": False,
                },
            }]
    except Exception as e:
        Log.err(f"TXT okuma hatası ({filepath.name}): {e}")
    return []


# ═════════════════════════════════════════════════════════════
#  QWEN 2.5 TEMİZLEME (Ollama — Yerel Beyin)
# ═════════════════════════════════════════════════════════════
CLEAN_PROMPT_TEMPLATE = """You are a document cleaning assistant. Clean the following raw text extracted from a PDF document.

Rules:
1. Fix broken, merged, or split words caused by PDF extraction
2. If you see table data, convert it to a clean Markdown table format
3. Remove repeated headers, footers, and page numbers
4. Preserve the original language exactly (Turkish, Spanish, English)
5. Do NOT add any information not present in the original text
6. Do NOT summarize — preserve ALL original content
7. Output ONLY the cleaned text, nothing else

Raw text:
{raw_text}"""


def init_qwen():
    """Ollama üzerinde Qwen 2.5 bağlantısını kur."""
    global OllamaLLM
    try:
        from langchain_ollama import OllamaLLM as _OllamaLLM
        OllamaLLM = _OllamaLLM
    except ImportError:
        Log.warn("langchain-ollama paketi yüklü değil. 'pip install langchain-ollama'")
        return None

    try:
        llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0.0, num_ctx=4096)
        llm.invoke("Merhaba")  # Bağlantı testi
        Log.ok(f"Qwen 2.5 ({OLLAMA_MODEL}) bağlantısı kuruldu ✓")
        return llm
    except Exception as e:
        Log.warn(f"Ollama bağlantısı kurulamadı: {e}")
        Log.warn("Metin temizleme atlanacak, ham metin kullanılacak.")
        return None


def clean_with_qwen(llm, text: str, max_chars: int = 2500) -> str:
    """Metni Qwen 2.5 ile temizle. Uzun metinleri parçalar halinde işler."""
    if not text or len(text) < 50:
        return text

    # Uzun metinleri parçalara böl (Qwen context sınırı)
    if len(text) > max_chars:
        parts = []
        for i in range(0, len(text), max_chars):
            chunk = text[i : i + max_chars]
            try:
                cleaned = llm.invoke(CLEAN_PROMPT_TEMPLATE.format(raw_text=chunk))
                parts.append(cleaned.strip())
            except Exception:
                parts.append(chunk)
        return "\n\n".join(parts)

    try:
        cleaned = llm.invoke(CLEAN_PROMPT_TEMPLATE.format(raw_text=text))
        return cleaned.strip()
    except Exception:
        return text


# ═════════════════════════════════════════════════════════════
#  CHUNK CACHE (Artımlı İnşa İçin)
# ═════════════════════════════════════════════════════════════
def save_chunks_cache(digest: str, chunks: list[dict]):
    """İşlenmiş chunk'ları diske cache'le."""
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_DIR / f"{digest}.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)


def load_chunks_cache(digest: str) -> list[dict] | None:
    """Cache'den chunk'ları yükle."""
    path = CACHE_DIR / f"{digest}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def delete_cache(digest: str):
    """Cache dosyasını sil."""
    path = CACHE_DIR / f"{digest}.json"
    if path.exists():
        path.unlink()


# ═════════════════════════════════════════════════════════════
#  TEK DOSYA İŞLEME BİRİMİ
# ═════════════════════════════════════════════════════════════
def process_file(filepath: Path, digest: str, qwen, splitter) -> list[Document]:
    """
    Tek bir dosyayı tamamen işle:
      dosya → çıkarma → Qwen temizleme → chunking → cache → Document listesi
    """
    # 1. Çıkarma
    suffix = filepath.suffix.lower()
    if suffix == ".pdf":
        pages = extract_pdf(filepath)
    elif suffix == ".txt":
        pages = extract_txt(filepath)
    else:
        pages = extract_docx(filepath)

    if not pages:
        return []

    # 2. Qwen Temizleme
    if qwen:
        for pg in pages:
            pg["text"] = clean_with_qwen(qwen, pg["text"])

    # 3. Chunking
    file_chunks: list[Document] = []
    for pg in pages:
        doc = Document(page_content=pg["text"], metadata=pg["metadata"])
        file_chunks.extend(splitter.split_documents([doc]))

    # 4. Cache'e yaz
    cache_data = [{"text": c.page_content, "metadata": c.metadata} for c in file_chunks]
    save_chunks_cache(digest, cache_data)

    return file_chunks


# ═════════════════════════════════════════════════════════════
#  ANA PİPELINE
# ═════════════════════════════════════════════════════════════
def build_pipeline(force_rebuild: bool = False, skip_llm: bool = False):
    """v1.5 Akıllı Veri İşleme Hattı — Ana fonksiyon."""

    Log.banner()
    t0 = time.time()

    # ──────────────────────────────────────────
    #  AŞAMA 1 — Dosya Keşfi & Değişiklik Analizi
    # ──────────────────────────────────────────
    Log.step(1, "Dosya Keşfi & Değişiklik Analizi")

    if not INPUT_DIR.exists():
        Log.err(f"'{INPUT_DIR}' klasörü bulunamadı!")
        return

    all_files = sorted(
        [f for f in INPUT_DIR.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    )
    if not all_files:
        Log.err(f"'{INPUT_DIR}' içinde desteklenen belge yok!")
        return

    Log.ok(f"{len(all_files)} belge bulundu")

    tracker = FileTracker(HASH_FILE)

    if force_rebuild:
        Log.warn("--rebuild bayrağı aktif → tüm dosyalar yeniden işlenecek")
        clf = {
            "new": [(f, tracker.md5(f)) for f in all_files],
            "changed": [],
            "unchanged": [],
            "deleted": list(tracker.records.keys()),
        }
    else:
        clf = tracker.classify(all_files)

    n_new = len(clf["new"])
    n_chg = len(clf["changed"])
    n_unc = len(clf["unchanged"])
    n_del = len(clf["deleted"])

    Log.ok(f"  [+] Yeni: {n_new}  |  [~] Degisen: {n_chg}  |  [=] Ayni: {n_unc}  |  [-] Silinen: {n_del}")

    to_process = clf["new"] + clf["changed"]
    needs_rebuild = force_rebuild or n_chg > 0 or n_del > 0

    if not to_process and not needs_rebuild:
        Log.ok("Tum dosyalar guncel -- islem gerekmiyor.")
        Log.ok(f"Sure: {time.time() - t0:.1f}s")
        return

    # ──────────────────────────────────────────
    #  AŞAMA 2 — Belge Okuma & Tablo Çıkarma
    # ──────────────────────────────────────────
    Log.step(2, "Belge Okuma & Tablo Çıkarma")

    if not OCR_AVAILABLE:
        Log.warn("pytesseract/pdf2image yüklü değil — OCR devre dışı")

    # ──────────────────────────────────────────
    #  AŞAMA 3 — Qwen 2.5 Metin Temizleme
    # ──────────────────────────────────────────
    Log.step(3, "Qwen 2.5 ile Metin Temizleme")

    qwen = None
    if not skip_llm:
        qwen = init_qwen()
    else:
        Log.warn("--no-llm bayrağı aktif → Qwen temizleme atlanıyor")

    # ──────────────────────────────────────────
    #  AŞAMA 4 — Dosya İşleme & Chunking
    # ──────────────────────────────────────────
    Log.step(4, "Dosya İşleme & Akıllı Chunking")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    new_chunks: list[Document] = []

    for idx, (fp, digest) in enumerate(to_process):
        Log.progress(idx + 1, len(to_process), fp.name)
        file_docs = process_file(fp, digest, qwen, splitter)
        new_chunks.extend(file_docs)
        tracker.update(fp, digest, len(file_docs))

    Log.ok(f"{len(new_chunks)} yeni chunk oluşturuldu ({len(to_process)} dosyadan)")

    # ──────────────────────────────────────────
    #  AŞAMA 5 — OpenAI Embedding
    # ──────────────────────────────────────────
    Log.step(5, "OpenAI Embedding Oluşturma")
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    # ──────────────────────────────────────────
    #  AŞAMA 6 — FAISS Veritabanı Güncelleme
    # ──────────────────────────────────────────
    Log.step(6, "FAISS Veritabanı Güncelleme")

    if needs_rebuild:
        # ── Yeniden İnşa (değişen/silinen dosyalar var) ──
        Log.warn("Değişen/silinen dosya tespit edildi → FAISS yeniden inşa ediliyor")

        all_chunks: list[Document] = []

        # Değişmeyen dosyaların chunk'larını cache'den yükle
        for fp, digest in clf["unchanged"]:
            cached = load_chunks_cache(digest)
            if cached:
                for c in cached:
                    all_chunks.append(
                        Document(page_content=c["text"], metadata=c["metadata"])
                    )
            else:
                # Cache yok → yeniden işle (ilk v1.5 çalıştırma senaryosu)
                Log.warn(f"  Cache bulunamadı, yeniden işleniyor: {fp.name}")
                docs = process_file(fp, digest, qwen, splitter)
                all_chunks.extend(docs)
                tracker.update(fp, digest, len(docs))

        # Yeni/değişen dosyaların chunk'larını ekle
        all_chunks.extend(new_chunks)

        # Silinen dosyaların kayıtlarını ve cache'lerini temizle
        for key in clf["deleted"]:
            old_md5 = tracker.records.get(key, {}).get("md5")
            if old_md5:
                delete_cache(old_md5)
            tracker.remove(key)

        if not all_chunks:
            Log.err("Hiç chunk oluşturulamadı!")
            return

        Log.ok(f"Toplam {len(all_chunks)} chunk ile FAISS yeniden inşa ediliyor...")
        vectorstore = FAISS.from_documents(all_chunks, embeddings)
        vectorstore.save_local(str(OUTPUT_DIR))

    else:
        # ── Artımlı Ekleme (sadece yeni dosyalar) ──
        if not new_chunks:
            Log.err("Hiç chunk oluşturulamadı!")
            return

        faiss_exists = (OUTPUT_DIR / "index.faiss").exists()

        if faiss_exists:
            Log.ok("Mevcut FAISS veritabanına ekleniyor (append)...")
            existing = FAISS.load_local(
                str(OUTPUT_DIR), embeddings, allow_dangerous_deserialization=True
            )
            new_db = FAISS.from_documents(new_chunks, embeddings)
            existing.merge_from(new_db)
            existing.save_local(str(OUTPUT_DIR))
            Log.ok(f"  {len(new_chunks)} chunk mevcut veritabanına eklendi")
        else:
            Log.ok("Yeni FAISS veritabanı oluşturuluyor...")
            vectorstore = FAISS.from_documents(new_chunks, embeddings)
            vectorstore.save_local(str(OUTPUT_DIR))

    # ── Tracker'ı kaydet ──
    tracker.save()

    elapsed = time.time() - t0
    print(f"\n{Log._G}{Log._B}{'=' * 55}")
    print(f"  Pipeline basariyla tamamlandi!")
    print(f"  Toplam sure : {elapsed:.1f}s")
    print(f"  FAISS index : {OUTPUT_DIR}/")
    print(f"  Hash kayit  : {HASH_FILE}")
    print(f"  Chunk cache : {CACHE_DIR}/")
    print(f"{'=' * 55}{Log._E}")


# ═════════════════════════════════════════════════════════════
#  GİRİŞ NOKTASI
# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="v1.5 Erasmus Akıllı Veri İşleme Hattı"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Tüm dosyaları sıfırdan yeniden işle ve FAISS'i yeniden inşa et",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Qwen 2.5 metin temizleme adımını atla (hızlı test için)",
    )
    args = parser.parse_args()

    build_pipeline(force_rebuild=args.rebuild, skip_llm=args.no_llm)
