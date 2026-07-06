#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  FAISS INDEX DEDUPLIKASYON ARACI                              ║
║  Otonom Erasmus Yapay Zeka Mentorluk Projesi                  ║
╚══════════════════════════════════════════════════════════════╝

Amaç:
  Mevcut FAISS index'inde birebir aynı (exact-duplicate) içerikli
  chunk'ları tespit edip temizler. Case-folding veya fuzzy/near-dup
  eşleştirme YAPILMAZ — yalnızca normalize edilmiş metin birebir
  aynıysa duplicate sayılır.

Dedup anahtarı:
  norm = " ".join(doc.page_content.split())
  key  = hashlib.md5(norm.encode("utf-8")).hexdigest()

İterasyon sırası:
  vs.index_to_docstore_id sözlüğünün anahtarları (FAISS pozisyonları)
  0..ntotal-1 sırasıyla gezilir → docstore._dict[doc_id] okunur.
  Her benzersiz key için İLK görülen Document (içerik + metadata dahil)
  korunur.

Kullanım:
  python dedup_index.py            # DRY-RUN: sadece istatistik yazdırır
  python dedup_index.py --apply    # Gerçek temizleme + index swap
"""

import os
import sys
import shutil
import hashlib
import argparse
from pathlib import Path

# Windows terminal UTF-8 encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    # Script repo kökünde durmuyor olabilir — açık yol ile tekrar dene
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

INDEX_DIR = Path("./faiss_index")
NEW_INDEX_DIR = Path("./faiss_index_new")
BACKUP_DIR = Path("./faiss_index_backup")
EMBEDDING_MODEL = "text-embedding-3-small"


# ═════════════════════════════════════════════════════════════
#  YARDIMCI: Renkli Terminal Çıktısı
# ═════════════════════════════════════════════════════════════
class Log:
    """Renkli ve yapılandırılmış terminal çıktıları."""

    if sys.platform == "win32":
        os.system("")  # Windows 10+ ANSI escape aktifleştirme

    _C = "\033[96m"
    _G = "\033[92m"
    _Y = "\033[93m"
    _R = "\033[91m"
    _B = "\033[1m"
    _E = "\033[0m"

    @staticmethod
    def banner():
        print(f"""{Log._C}{Log._B}
+==============================================================+
|  [*] FAISS INDEX DEDUPLIKASYON ARACI                          |
+==============================================================+{Log._E}""")

    @staticmethod
    def step(num, total, msg):
        print(f"\n{Log._B}[Aşama {num}/{total}]{Log._E} {Log._C}{msg}{Log._E}")

    @staticmethod
    def ok(msg):
        print(f"  {Log._G}[OK]{Log._E} {msg}")

    @staticmethod
    def warn(msg):
        print(f"  {Log._Y}[!]{Log._E} {msg}")

    @staticmethod
    def err(msg):
        print(f"  {Log._R}[X]{Log._E} {msg}")


# ═════════════════════════════════════════════════════════════
#  ORTAK: Index'ten sıralı Document listesi çıkarma + dedup
# ═════════════════════════════════════════════════════════════
def load_ordered_documents(vs: FAISS) -> list[Document]:
    """
    FAISS index'indeki tüm dokümanları, vektör pozisyon sırasına göre
    (0..ntotal-1) döndürür.
    """
    docs: list[Document] = []
    n_total = vs.index.ntotal
    for pos in range(n_total):
        doc_id = vs.index_to_docstore_id[pos]
        doc = vs.docstore._dict[doc_id]
        docs.append(doc)
    return docs


def dedup_documents(docs: list[Document]):
    """
    Exact-duplicate temizleme.
    Döner: (unique_docs, total_count, duplicate_count, dup_group_count)
    """
    seen_keys: set[str] = set()
    unique_docs: list[Document] = []
    key_counts: dict[str, int] = {}

    for doc in docs:
        norm = " ".join(doc.page_content.split())
        key = hashlib.md5(norm.encode("utf-8")).hexdigest()
        key_counts[key] = key_counts.get(key, 0) + 1
        if key not in seen_keys:
            seen_keys.add(key)
            unique_docs.append(doc)

    total = len(docs)
    unique_count = len(unique_docs)
    duplicate_count = total - unique_count
    dup_group_count = sum(1 for c in key_counts.values() if c > 1)

    return unique_docs, total, duplicate_count, dup_group_count


# ═════════════════════════════════════════════════════════════
#  DOĞRULAMA (--apply içinde, swap'tan ÖNCE)
# ═════════════════════════════════════════════════════════════
def verify_new_index(expected_unique_count: int) -> bool:
    """
    faiss_index_new/ içindeki yeni index'i yükleyip doğrular:
      1. chunk sayısı == beklenen benzersiz sayı
      2. tüm chunk'larda metadata university == "UJA"
      3. örnek arama sonuçlarının içerikleri birbirinden farklı
    Başarısızsa False döner, swap YAPILMAMALI.
    """
    Log.step(4, 5, "Doğrulama (faiss_index_new/ üzerinde)")

    try:
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        vs_new = FAISS.load_local(
            str(NEW_INDEX_DIR), embeddings, allow_dangerous_deserialization=True
        )
    except Exception as e:
        Log.err(f"Yeni index yüklenemedi: {e}")
        return False

    # 1) Sayı kontrolü
    actual_count = vs_new.index.ntotal
    if actual_count != expected_unique_count:
        Log.err(
            f"Chunk sayısı uyuşmuyor! beklenen={expected_unique_count} "
            f"gerçek={actual_count}"
        )
        return False
    Log.ok(f"Chunk sayısı doğru: {actual_count}")

    # 2) university == "UJA" kontrolü
    new_docs = load_ordered_documents(vs_new)
    non_uja = [d for d in new_docs if d.metadata.get("university") != "UJA"]
    if non_uja:
        Log.err(f"{len(non_uja)} chunk'ta university != 'UJA' bulundu!")
        return False
    Log.ok(f"Tüm {len(new_docs)} chunk'ta university == 'UJA'")

    # 3) Örnek arama — 5 sonucun normalize içerikleri birbirinden farklı olmalı
    try:
        results = vs_new.similarity_search("Umove sistemi evrak", k=5)
    except Exception as e:
        Log.err(f"Örnek arama başarısız: {e}")
        return False

    norm_contents = [" ".join(r.page_content.split()) for r in results]
    if len(norm_contents) < 5:
        Log.err(f"Örnek arama yalnızca {len(norm_contents)} sonuç döndürdü (5 bekleniyordu)")
        return False

    if len(set(norm_contents)) != len(norm_contents):
        Log.err("Örnek aramadaki sonuçlar arasında birebir aynı içerik bulundu!")
        return False
    Log.ok(f"Örnek arama: {len(norm_contents)} sonucun tümü birbirinden farklı içerikte")

    return True


# ═════════════════════════════════════════════════════════════
#  --apply: RE-EMBED + YENİ INDEX + SWAP
# ═════════════════════════════════════════════════════════════
def apply_dedup(unique_docs: list[Document], total: int, duplicate_count: int):
    Log.step(3, 5, "Benzersiz Chunk'ları Re-embed Etme (OpenAI)")

    if NEW_INDEX_DIR.exists():
        Log.warn(f"{NEW_INDEX_DIR}/ zaten var, siliniyor...")
        shutil.rmtree(NEW_INDEX_DIR)

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    Log.ok(f"{len(unique_docs)} benzersiz chunk embed ediliyor...")
    vectorstore = FAISS.from_documents(unique_docs, embeddings)
    vectorstore.save_local(str(NEW_INDEX_DIR))
    Log.ok(f"Yeni index kaydedildi -> {NEW_INDEX_DIR}/")

    # ── Doğrulama ──
    if not verify_new_index(expected_unique_count=len(unique_docs)):
        Log.err("Doğrulama BAŞARISIZ! Swap yapılmadı, faiss_index/ olduğu gibi kalıyor.")
        Log.err(f"İncelemek isterseniz {NEW_INDEX_DIR}/ klasörü silinmedi, elle kontrol edin.")
        sys.exit(1)

    # ── Güvenlik: swap'tan önce backup yoksa oluştur (varsa DOKUNMA) ──
    Log.step(5, 5, "Swap: faiss_index/ Güncelleniyor")
    if not BACKUP_DIR.exists():
        Log.warn(f"{BACKUP_DIR}/ bulunamadı, mevcut index'ten oluşturuluyor...")
        shutil.copytree(INDEX_DIR, BACKUP_DIR)
        Log.ok(f"{BACKUP_DIR}/ oluşturuldu")
    else:
        Log.ok(f"{BACKUP_DIR}/ zaten mevcut, dokunulmadı")

    # ── Swap: faiss_index/ içeriğini yenisiyle değiştir ──
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    shutil.copytree(NEW_INDEX_DIR, INDEX_DIR)
    Log.ok(f"{INDEX_DIR}/ yeni (deduplike edilmiş) index ile değiştirildi")

    # ── Geçici klasörü temizle ──
    shutil.rmtree(NEW_INDEX_DIR)
    Log.ok(f"{NEW_INDEX_DIR}/ silindi")

    print(f"\n{Log._G}{Log._B}{'=' * 55}")
    print(f"  Dedup + swap başarıyla tamamlandı!")
    print(f"  Toplam (eski)      : {total}")
    print(f"  Benzersiz (yeni)   : {len(unique_docs)}")
    print(f"  Elenen duplicate   : {duplicate_count}")
    print(f"  Canlı index        : {INDEX_DIR}/")
    print(f"{'=' * 55}{Log._E}")


# ═════════════════════════════════════════════════════════════
#  ANA AKIŞ
# ═════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="FAISS index'indeki exact-duplicate chunk'ları temizler."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Gerçek temizlemeyi uygula (re-embed + yeni index + swap). "
             "Bayraksız çalıştırma yalnızca istatistik gösterir (dry-run).",
    )
    args = parser.parse_args()

    Log.banner()

    if not INDEX_DIR.exists() or not (INDEX_DIR / "index.faiss").exists():
        Log.err(f"'{INDEX_DIR}' bulunamadı veya geçersiz!")
        sys.exit(1)

    # ── Aşama 1: Mevcut index'i yükle ──
    Log.step(1, 5 if args.apply else 2, "Mevcut FAISS Index Yükleniyor")
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vs = FAISS.load_local(
        str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True
    )
    Log.ok(f"Index yüklendi: {vs.index.ntotal} chunk")

    # ── Aşama 2: Dedup analizi ──
    Log.step(2, 5 if args.apply else 2, "Duplicate Analizi")
    docs = load_ordered_documents(vs)
    unique_docs, total, duplicate_count, dup_group_count = dedup_documents(docs)

    print()
    Log.ok(f"Toplam chunk        : {total}")
    Log.ok(f"Benzersiz chunk      : {len(unique_docs)}")
    Log.ok(f"Elenecek duplicate   : {duplicate_count}")
    Log.ok(f"Duplicate grup sayısı: {dup_group_count}")

    if not args.apply:
        print(f"\n{Log._Y}{Log._B}DRY-RUN modu — hiçbir dosya değiştirilmedi.")
        print(f"Gerçek temizleme için: python dedup_index.py --apply{Log._E}")
        return

    if duplicate_count == 0:
        Log.ok("Hiç duplicate yok, yapılacak işlem bulunmuyor.")
        return

    apply_dedup(unique_docs, total, duplicate_count)


if __name__ == "__main__":
    main()
