#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Erasmus++ — Değerlendirme v2 (eval_v2.py)
=========================================

synthetic_stress_test_ultra.py temel alınarak yazıldı; şu düzeltmelerle:

  a) Hakem modeli (JUDGE_MODEL) cevap veren modelden (ai_engine.GROQ_MODEL)
     FARKLIDIR. Aynı model girilirse script çalışmayı reddeder.
  b) Soru seti FAISS docstore'undaki info_bank chunk'larından üretilir ve
     eval_v2_questions.json içine DONDURULUR (soru, beklenen cevap, kanıt
     alıntısı, kaynak dosya, sayfa). Soruların ~%20'si belgelerde cevabı
     OLMAYAN sorulardır (doğru davranış: fallback / ret).
  c) Her cevap dört sınıftan birine konur:
        DOĞRU CEVAP | DOĞRU RET | GEREKSİZ RET | HALÜSİNASYON
  d) İstekler arasında rate-limit beklemesi vardır; 429 / geçici hata
     durumunda otomatik tekrar denenir. Her soru sonrası sonuç
     eval_v2_results.jsonl dosyasına yazılır; script yarıda kesilirse
     kaldığı yerden devam eder.

Yan etki izolasyonu (ai_engine.py DEĞİŞTİRİLMEDEN):
  - Sohbet hafızası: memory_store.DB_PATH, ai_engine import edilmeden önce
    ayrı bir dosyaya (eval_v2_chat_memory.db) yönlendirilir; her soru
    benzersiz bir user_id ile ve boş geçmişle sorulur.
  - eksik_sorular.txt: bot bir soruya fallback verdiğinde bu dosyaya satır
    ekler. Değerlendirme soruları gerçek kullanıcı loguna karışmasın diye her
    çağrıdan önce dosya içeriği alınır ve çağrıdan sonra geri yazılır.

FAISS index'e ve ai_engine.py'ye yalnızca OKUMA amaçlı erişilir.

Kullanım:
    python eval_v2.py generate   # soru setini üret (varsa devam eder)
    python eval_v2.py run        # botu çalıştır + hakem (kaldığı yerden)
    python eval_v2.py report     # eval_v2_rapor.md üret
    python eval_v2.py all        # hepsi sırayla (varsayılan)
"""

import os
import re
import sys
import json
import time
import random
import asyncio
import hashlib
import sqlite3
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # ai_engine göreli yollar kullanıyor (./faiss_index, eksik_sorular.txt)

# ── Hafıza izolasyonu: ai_engine import edilmeden ÖNCE ──
import memory_store  # noqa: E402

EVAL_MEMORY_DB = ROOT / "eval_v2_chat_memory.db"
memory_store.DB_PATH = str(EVAL_MEMORY_DB)

import ai_engine  # noqa: E402
from ai_engine import get_ai_response, GROQ_MODEL  # noqa: E402
from groq import AsyncGroq  # noqa: E402

# ═════════════════════════════════════════════════════════════
#  AYARLAR
# ═════════════════════════════════════════════════════════════
ANSWER_MODEL = GROQ_MODEL                       # botun kullandığı model (ai_engine'den)
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "qwen/qwen3.8-27b")
GEN_MODEL = os.getenv("EVAL_GEN_MODEL", JUDGE_MODEL)  # soru üretimi de botun modeli değil

SEED = 42
N_ANSWERABLE = 40
N_UNANSWERABLE = 10   # 10 / 50 = %20

QUESTIONS_FILE = ROOT / "eval_v2_questions.json"
# EVAL_RUN verilirse sonuç/rapor ayrı dosyalara yazılır (baseline korunur),
# ör. EVAL_RUN=adim1 → eval_v2_results_adim1.jsonl, eval_v2_rapor_adim1.md
EVAL_RUN = os.getenv("EVAL_RUN", "").strip()
_SUFFIX = f"_{EVAL_RUN}" if EVAL_RUN else ""
RESULTS_FILE = ROOT / f"eval_v2_results{_SUFFIX}.jsonl"
REPORT_FILE = ROOT / f"eval_v2_rapor{_SUFFIX}.md"
EKSIK_LOG = ROOT / "eksik_sorular.txt"
USER_ID_BASE = 7_200_000

# Groq ücretsiz katman: her model için 8000 TPM. Bot çağrısı ~4.5-5k token,
# hakem çağrısı ~4-6k token harcıyor → aynı modele iki çağrı arası ≥ ~40 sn.
WAIT_AFTER_ANSWER = 25   # bot çağrısından sonra (ardından hakem çağrısı gelir)
WAIT_AFTER_JUDGE = 25    # hakem çağrısından sonra (ardından sonraki bot çağrısı)
WAIT_AFTER_GEN = 8       # soru üretimi (~1.5k token)
MAX_RETRIES = 6

TECH_ERROR_REPLY = "teknik bir aksaklık"  # ai_engine'in exception fallback'i

# test_ai.py ile aynı mantık; yalnızca hakemle çapraz kontrol için kaydedilir.
FALLBACK_MARKERS = ["rehberde yok", "teyit etmen lazım", "bilgi yok"]

LABELS = ["DOĞRU CEVAP", "DOĞRU RET", "GEREKSİZ RET", "HALÜSİNASYON"]

# Kaynak dosya başına cevaplı soru kotası (toplam 40). Ağırlıklar chunk
# sayısına ve öğrenci açısından önemine göre seçildi; yalnızca piyasa/
# araştırma niteliğindeki üç belge bilinçli olarak az temsil ediliyor.
SOURCE_QUOTA = {
    "2025 PROJE DÖNEMİ (2026-2027 Akademik Yılı) ERASMUS ÖĞRENİM HAREKETLİLİĞİ İLANI – AB Eğitim Programları Koordinatörlüğü.pdf": 5,
    "UJAINTERNATIONALGUIDE.pdf": 5,
    "Procedures in the UJA_incoming mobility.docx": 4,
    "Erasmus+ Öğrenci Bilgi Veri Seti Oluşturma.pdf": 3,
    "OGRENIM-HAREKETLILIGI-YOL-HARITASI.pdf": 3,
    "Ogrenim-Yol-Haritasi-2024-proje-donemi.docx-SON.pdf": 3,
    "InstruccionesParaLaTramitacionErasmus2022-23.pdf": 2,
    "PROTOCOL EMERGENCIES_STUDENTS MOBILITY.docx.pdf": 2,
    "national_SSU_SLU_Student.pdf": 2,
    "CG202324_anexo10_Calendario_académico_2025_2026_Aprobado.pdf": 2,
    "2026-2027 Erasmus Hibe Miktarları, Seyahat Destekleri ve Seçim Ölçütleri.txt": 2,
    "INCOMING MOBILITY STUDENTS. FREQUENTLY ASKED QUESTIONS ABOUT ACADEMIC CONTRACT AND ENROLLMENT AT UJA..pdf": 1,
    "_Información cursos de español CEALM 25-26 (Info para coordinadores, estudiantes y buddies).docx": 1,
    "2025 Proje Dönemi (2026-2027 Akademik Yılı) Erasmus Öğrenim Hareketliliği Nihai Sonuçları – AB Eğitim Programları Koordinatörlüğü.pdf": 1,
    "Erasmus+ Girişimi İçin Pazar Araştırması.pdf": 1,
    "Erasmus Grupları ve Öğrenci Sorunları Araştırması.pdf": 1,
    "Information of interest about Jaén and Linares.docx": 1,
    "actvivar cuenta TIC_incoming.docx": 1,
}
assert sum(SOURCE_QUOTA.values()) == N_ANSWERABLE

# Cevabı belgelerde OLMAYAN sorular. Elle yazıldı; her biri için anahtar
# kelimeler tüm chunk'larda regex ile arandı (0 alakalı eşleşme) ve
# generate aşamasında ayrıca "retrieval + hakem" ile yokluk doğrulanıyor.
UNANSWERABLE = [
    {"soru": "UJA kampüsündeki yemekhanede (comedor) günün menüsü kaç euro?",
     "kontrol_regex": r"comedor|yemekhane|cafeter|men[uú] del d"},
    {"soru": "Erasmus sırasında İspanya'da öğrenci olarak haftada en fazla kaç saat yarı zamanlı çalışabilirim?",
     "kontrol_regex": r"çalışabil|yarı zamanlı|part-time|trabajar|work permit"},
    {"soru": "Türk ehliyetimle İspanya'da kaç ay boyunca araba kullanabilirim?",
     "kontrol_regex": r"ehliyet|driving licen|permiso de conducir|licencia de conducir"},
    {"soru": "Erasmus'a gitmeden önce askerlik tecilim için askerlik şubesine hangi belgeyi vermem gerekiyor?",
     "kontrol_regex": r"asker|tecil|military"},
    {"soru": "Jaén'de belediyenin bisiklet kiralama sistemi var mı, aylık ücreti ne kadar?",
     "kontrol_regex": r"bisiklet|bicicleta|bicycle|bike"},
    {"soru": "UJA kampüsünde öğrenciler için otopark ücreti ne kadar?",
     "kontrol_regex": r"parking|aparcamiento|otopark"},
    {"soru": "UJA'nın kapalı yüzme havuzunu Erasmus öğrencileri kaç euroya kullanabiliyor?",
     "kontrol_regex": r"piscina|swimming|yüzme"},
    {"soru": "UJA öğrenci kartıyla Jaén şehir otobüslerinde yüzde kaç indirim alıyorum?",
     "kontrol_regex": r"(bus|otobüs|autob)[^.]{0,80}(indirim|discount|descuento|bono)"},
    {"soru": "Jaén'den Madrid'e trenle gitmek kaç euro tutuyor?",
     "kontrol_regex": r"madrid[^.]{0,80}(€|euro|avro)"},
    {"soru": "UJA'da Erasmus öğrencileri için yaz okulu (curso de verano) var mı, ücreti ne kadar?",
     "kontrol_regex": r"yaz okulu|curso de verano|summer school|summer course"},
]
assert len(UNANSWERABLE) == N_UNANSWERABLE

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))


# ═════════════════════════════════════════════════════════════
#  Yardımcılar
# ═════════════════════════════════════════════════════════════
def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def extract_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def retry_wait(err: Exception, attempt: int) -> float:
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(err))
    if m:
        return float(m.group(1) or 0) * 60 + float(m.group(2)) + 2
    return min(15 * (attempt + 1), 90)


async def llm_call(model: str, prompt: str, temperature: float = 0.0) -> str:
    extra = {"reasoning_format": "hidden"} if model.startswith("qwen/") else {}
    for attempt in range(MAX_RETRIES):
        try:
            r = await client.chat.completions.create(
                model=model,
                temperature=temperature,
                seed=SEED,
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
            return r.choices[0].message.content or ""
        except Exception as e:  # 429, 5xx, ağ hatası
            w = retry_wait(e, attempt)
            log(f"  {model} hata ({type(e).__name__}): {str(e)[:120]} → {w:.0f}s bekle")
            time.sleep(w)
    raise RuntimeError(f"{model}: {MAX_RETRIES} denemede başarısız")


def load_chunks() -> list[dict]:
    """FAISS docstore'undaki tüm chunk'ları (salt okunur) index sırasıyla döndür."""
    vs = ai_engine.vectorstore
    out = []
    for pos, doc_id in sorted(vs.index_to_docstore_id.items()):
        d = vs.docstore.search(doc_id)
        out.append({
            "pos": pos,
            "source": nfc(d.metadata.get("source")),  # bazı dosya adları NFD
            "page": d.metadata.get("page"),
            "text": d.page_content,
        })
    return out


def retrieve_like_engine(question: str) -> list:
    """Botun gördüğü bağlam: ai_engine.retrieve_context ile birebir aynı
    fonksiyon (kopya değil), hakem botun gerçekten gördüğünü görür."""
    return ai_engine.retrieve_context(question, None)


def format_context(docs, max_chars: int = 9000) -> str:
    parts = [f"[Kaynak {i} | {d.metadata.get('source')} | s.{d.metadata.get('page')}]\n{d.page_content}"
             for i, d in enumerate(docs, 1)]
    ctx = "\n\n---\n\n".join(parts)
    return ctx if len(ctx) <= max_chars else ctx[:max_chars] + "\n[...kırpıldı]"


def file_md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def git_state() -> dict:
    def g(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True,
                                  cwd=ROOT, encoding="utf-8").stdout.strip()
        except Exception:
            return "?"
    return {
        "commit": g("rev-parse", "--short", "HEAD"),
        "ai_engine_degisiklik_var": bool(g("status", "--porcelain", "ai_engine.py")),
    }


# ═════════════════════════════════════════════════════════════
#  AŞAMA 1: Soru seti üretimi
# ═════════════════════════════════════════════════════════════
GEN_PROMPT = """Bir RAG sistemini değerlendirmek için soru-cevap çifti hazırlıyorsun.
Aşağıda Erasmus/Universidad de Jaén (UJA) ile ilgili resmi veya bilgilendirici bir belgeden alınmış bir metin parçası var.
Belge: {source} (sayfa {page})

GÖREV: Bu metindeki SOMUT bir bilgiye (rakam, tarih, belge adı, prosedür adımı, iletişim bilgisi, kural) dayanan,
Türkçe konuşan bir Erasmus öğrencisinin Telegram botuna gerçekten sorabileceği 1 soru üret.

KURALLAR:
1. Soru tek başına anlaşılır olmalı: "bu metinde", "belgeye göre", "yukarıda" gibi ifadeler KULLANMA. Gerekirse UJA, Jaén, Erasmus gibi bağlamı soruya yaz.
2. Sorunun cevabı bu metinde AÇIKÇA bulunmalı ve kısa olmalı (bir cümle veya kısa liste).
3. Soru Türkçe olsun (İspanyolca/İngilizce özel terimler aynen kalabilir).
4. "kanit_alinti" alanına cevabı içeren cümleyi metinden KELİMESİ KELİMESİNE kopyala (çevirme, düzeltme).
5. Metin içindekiler tablosu, kaynakça, anlamsız parça veya öğrenciye faydasız ise "uygun": false döndür.

SADECE şu JSON'u döndür:
{{"uygun": true, "soru": "...", "beklenen_cevap": "...", "kanit_alinti": "..."}}

METİN:
\"\"\"{text}\"\"\"
"""

ABSENCE_PROMPT = """Aşağıdaki soru ve bir arama sisteminin bu soru için getirdiği belge parçaları var.
Görevin: Bu parçalardan HERHANGİ biri sorunun spesifik cevabını (istenen rakam/kural/bilgi) içeriyor mu?
Sadece genel olarak ilgili olması yetmez; sorulan spesifik bilgi açıkça yazıyor olmalı.

SORU: {soru}

PARÇALAR:
{context}

SADECE şu JSON'u döndür: {{"cevap_var": true/false, "aciklama": "kısa"}}
"""


async def generate_questions() -> list[dict]:
    data = {"meta": {}, "questions": []}
    if QUESTIONS_FILE.exists():
        data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    qs = data["questions"]
    done_ids = {q["id"] for q in qs}

    def save():
        data["meta"] = {
            **data.get("meta", {}),  # elle eklenen alanlar (ör. manuel_duzenlemeler) korunur
            "olusturma_tarihi": data.get("meta", {}).get("olusturma_tarihi") or datetime.now().isoformat(timespec="seconds"),
            "uretici_model": GEN_MODEL,
            "seed": SEED,
            "faiss_index_md5": file_md5(ROOT / "faiss_index" / "index.faiss"),
            "not": "Cevaplı sorular FAISS docstore chunk'larından LLM ile üretildi; "
                   "kanıt alıntısı chunk içinde birebir doğrulandı. Cevapsız sorular elle yazıldı.",
        }
        QUESTIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    chunks = load_chunks()
    rng = random.Random(SEED)

    # ── Cevaplı sorular ──
    for src, quota in SOURCE_QUOTA.items():
        have = [q for q in qs if q["tur"] == "cevapli" and q["kaynak_dosya"] == src]
        if len(have) >= quota:
            continue
        pool = [c for c in chunks if c["source"] == src and len(c["text"].strip()) >= 300]
        if not pool:
            log(f"UYARI: {src} için uygun chunk yok")
            continue
        rng_src = random.Random(f"{SEED}-{src}")  # kaynak bazlı deterministik sıra
        rng_src.shuffle(pool)
        used_pos = {q.get("chunk_pos") for q in qs}
        for c in pool:
            if len(have) >= quota:
                break
            if c["pos"] in used_pos:
                continue
            prompt = GEN_PROMPT.format(source=src, page=c["page"], text=c["text"][:2500])
            raw = await llm_call(GEN_MODEL, prompt, temperature=0.0)
            time.sleep(WAIT_AFTER_GEN)
            j = extract_json(raw)
            if not j or not j.get("uygun") or not j.get("soru") or not j.get("beklenen_cevap"):
                continue
            alinti = (j.get("kanit_alinti") or "").strip()
            # Kanıt alıntısı chunk içinde birebir (boşluk normalize) geçmeli
            if len(alinti) < 15 or norm_ws(alinti) not in norm_ws(c["text"]):
                log(f"  alıntı chunk'ta bulunamadı, atlandı: {src[:40]} s.{c['page']}")
                continue
            qid = f"A{len([q for q in qs if q['tur'] == 'cevapli']) + 1:02d}"
            qs.append({
                "id": qid,
                "tur": "cevapli",
                "soru": j["soru"].strip(),
                "beklenen_cevap": j["beklenen_cevap"].strip(),
                "kanit_alinti": alinti,
                "kaynak_dosya": src,
                "sayfa": c["page"],
                "chunk_pos": c["pos"],
            })
            have.append(qs[-1])
            used_pos.add(c["pos"])
            save()
            log(f"  {qid} ← {src[:45]} s.{c['page']}: {j['soru'][:80]}")

    # ── Cevapsız sorular ──
    for i, u in enumerate(UNANSWERABLE, 1):
        qid = f"U{i:02d}"
        if qid in done_ids:
            continue
        rx = re.compile(u["kontrol_regex"], re.I)
        grep_hits = [f"{c['source']} s.{c['page']}" for c in chunks if rx.search(c["text"])]
        docs = ai_engine._retrieve(u["soru"], 8, None)
        raw = await llm_call(JUDGE_MODEL, ABSENCE_PROMPT.format(soru=u["soru"], context=format_context(docs, 8000)))
        time.sleep(WAIT_AFTER_JUDGE)
        j = extract_json(raw) or {}
        qs.append({
            "id": qid,
            "tur": "cevapsiz",
            "soru": u["soru"],
            "beklenen_cevap": "Belgelerde bu bilgi yok; doğru davranış fallback (bilmiyorum / koordinatöre yönlendirme).",
            "kanit_alinti": None,
            "kaynak_dosya": None,
            "sayfa": None,
            "yokluk_kontrolu": {
                "regex": u["kontrol_regex"],
                "regex_eslesmeleri": grep_hits,
                "retrieval_top8_hakem_cevap_var": j.get("cevap_var"),
                "hakem_aciklama": j.get("aciklama"),
            },
        })
        save()
        flag = "  ⚠ KONTROL ET" if grep_hits or j.get("cevap_var") else ""
        log(f"  {qid} yokluk: regex={len(grep_hits)} hakem_cevap_var={j.get('cevap_var')}{flag}")

    save()
    log(f"Soru seti: {QUESTIONS_FILE.name} ({len(qs)} soru)")
    return qs


# ═════════════════════════════════════════════════════════════
#  AŞAMA 2: Bot + Hakem
# ═════════════════════════════════════════════════════════════
JUDGE_PROMPT = """Sen titiz ve tarafsız bir RAG değerlendirme hakemisin. Bir Erasmus asistan botunun cevabını sınıflandıracaksın.

[SORU]
{soru}

[SORUNUN CEVABI BELGELERDE VAR MI?]
{cevap_var_mi}

[BEKLENEN CEVAP]
{beklenen}

[KANIT (kaynak belgeden birebir alıntı)]
{kanit}

[BOTUN O SORU İÇİN GÖRDÜĞÜ BELGE PARÇALARI]
{context}

[BOTUN CEVABI]
{cevap}

SINIFLAR — tam olarak birini seç:
- "DOĞRU CEVAP": Cevap belgelerde VAR ve bot beklenen cevabın ÖZÜNÜ (ana rakam/kural/bilgi) doğru verdi. Ek bilgiler belge parçalarıyla destekleniyorsa veya zararsız genel tavsiyeyse sorun değil. Sonda "koordinatörden teyit et" demesi DOĞRU CEVAP olmasını engellemez.
- "DOĞRU RET": Cevap belgelerde YOK ve bot spesifik bir bilgi uydurmadan bilmediğini söyledi / yönlendirdi.
- "GEREKSİZ RET": Cevap belgelerde VAR ama bot bilgiyi vermeyip "rehberde yok / bilmiyorum / koordinatöre sor" dedi.
- "HALÜSİNASYON": Bot beklenen cevapla ÇELİŞEN, yanlış ya da belge parçalarında ve kanıtta OLMAYAN spesifik bilgi (rakam, tarih, kurum, prosedür) verdi; VEYA cevap belgelerde yokken uydurma bir cevap verdi; VEYA ret etmeden konuyla ilgisiz/yanlış bir cevap verip asıl soruyu cevaplamadı.

"hata_alt_tipi" (sadece HALÜSİNASYON için): "uydurma" (belgede olmayan bilgi), "yanlis" (belgeyle çelişen bilgi) veya "eksik_alakasiz" (asıl bilgi yok ama ret de yok).

SADECE şu JSON'u döndür:
{{"sinif": "DOĞRU CEVAP|DOĞRU RET|GEREKSİZ RET|HALÜSİNASYON", "hata_alt_tipi": null, "gerekce": "1-2 cümle Türkçe"}}
"""


def normalize_label(s: str) -> str | None:
    s = (s or "").upper().replace("İ", "I")
    if "HAL" in s:
        return "HALÜSİNASYON"
    if "GEREKS" in s:
        return "GEREKSİZ RET"
    if "RET" in s:
        return "DOĞRU RET"
    if "DO" in s and "CEVAP" in s:
        return "DOĞRU CEVAP"
    return None


async def ask_bot(question: str, uid: int) -> str:
    """Botu çağırır; eksik_sorular.txt'yi korur; teknik hatada tekrar dener."""
    for attempt in range(MAX_RETRIES):
        # Her soru boş sohbet geçmişiyle sorulsun (yeniden koşularda da)
        with sqlite3.connect(EVAL_MEMORY_DB) as conn:
            conn.execute("DELETE FROM messages WHERE user_id = ?", (uid + attempt,))
        before = EKSIK_LOG.read_bytes() if EKSIK_LOG.exists() else None
        try:
            reply = await get_ai_response(question, user_id=uid + attempt)
        finally:
            if before is not None and EKSIK_LOG.read_bytes() != before:
                EKSIK_LOG.write_bytes(before)
        if TECH_ERROR_REPLY not in reply:
            return reply
        w = 30 * (attempt + 1)
        log(f"  bot teknik hata döndü (muhtemelen 429) → {w}s bekle, tekrar")
        time.sleep(w)
    # Kayıt yazmadan dur: günlük token limiti (TPD) gibi durumlarda soru
    # "HATA" olarak işaretlenip atlanmasın, sonraki `run` kaldığı yerden sorsun.
    sys.exit(f"Bot {MAX_RETRIES} denemede cevap üretemedi (muhtemelen Groq günlük token limiti). "
             "Limit açılınca `python eval_v2.py run` ile kaldığı yerden devam edin.")


async def run_eval(questions: list[dict]) -> None:
    done = {}
    if RESULTS_FILE.exists():
        for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r
    todo = [q for q in questions if q["id"] not in done]
    log(f"Değerlendirme: {len(done)} tamamlanmış, {len(todo)} kaldı")

    for n, q in enumerate(todo, 1):
        idx = questions.index(q)
        uid = USER_ID_BASE + idx * 10
        log(f"[{n}/{len(todo)}] {q['id']} {q['soru'][:80]}")

        t0 = time.time()
        cevap = await ask_bot(q["soru"], uid)
        sure = round(time.time() - t0, 1)
        time.sleep(WAIT_AFTER_ANSWER)

        docs = retrieve_like_engine(q["soru"])
        retrieved = [f"{d.metadata.get('source')} s.{d.metadata.get('page')}" for d in docs]
        kaynak_getirildi = None
        if q["tur"] == "cevapli":
            kaynak_getirildi = any(
                nfc(d.metadata.get("source")) == nfc(q["kaynak_dosya"]) and d.metadata.get("page") == q["sayfa"]
                and norm_ws(q["kanit_alinti"]) in norm_ws(d.page_content)
                for d in docs
            )

        if cevap.startswith("HATA:"):
            sinif, alt, gerekce, raw = "HATA", None, cevap, ""
        else:
            prompt = JUDGE_PROMPT.format(
                soru=q["soru"],
                cevap_var_mi="EVET" if q["tur"] == "cevapli" else "HAYIR — belgelerde bu bilgi yok.",
                beklenen=q["beklenen_cevap"],
                kanit=q["kanit_alinti"] or "(yok — soru belgelerde cevapsız)",
                context=format_context(docs, 9000),
                cevap=cevap[:4000],
            )
            sinif = None
            for _ in range(3):
                raw = await llm_call(JUDGE_MODEL, prompt)
                j = extract_json(raw) or {}
                sinif = normalize_label(j.get("sinif", ""))
                if sinif:
                    break
                time.sleep(10)
            alt = j.get("hata_alt_tipi") if sinif == "HALÜSİNASYON" else None
            gerekce = j.get("gerekce", "")
            if not sinif:
                sinif = "HATA"
                gerekce = f"Hakem çıktısı ayrıştırılamadı: {raw[:200]}"
            # Mantıksal tutarlılık: cevaplı soruda "DOĞRU RET", cevapsız soruda
            # "DOĞRU CEVAP"/"GEREKSİZ RET" olamaz → ilgili sınıfa eşle ve işaretle.
            if q["tur"] == "cevapli" and sinif == "DOĞRU RET":
                sinif, gerekce = "GEREKSİZ RET", "[eşlendi: DOĞRU RET→GEREKSİZ RET] " + gerekce
            if q["tur"] == "cevapsiz" and sinif == "GEREKSİZ RET":
                sinif, gerekce = "DOĞRU RET", "[eşlendi: GEREKSİZ RET→DOĞRU RET] " + gerekce
            if q["tur"] == "cevapsiz" and sinif == "DOĞRU CEVAP":
                sinif, gerekce = "HALÜSİNASYON", "[eşlendi: DOĞRU CEVAP→HALÜSİNASYON] " + gerekce
            time.sleep(WAIT_AFTER_JUDGE)

        rec = {
            "id": q["id"],
            "tur": q["tur"],
            "soru": q["soru"],
            "beklenen_cevap": q["beklenen_cevap"],
            "kaynak_dosya": q["kaynak_dosya"],
            "sayfa": q["sayfa"],
            "bot_cevabi": cevap,
            "sinif": sinif,
            "hata_alt_tipi": alt,
            "hakem_gerekce": gerekce,
            "heuristik_fallback": any(m in cevap.lower() for m in FALLBACK_MARKERS),
            "kaynak_chunk_getirildi": kaynak_getirildi,
            "getirilen_kaynaklar": retrieved,
            "cevap_suresi_sn": sure,
            "cevap_modeli": ANSWER_MODEL,
            "hakem_modeli": JUDGE_MODEL,
            "retrieval_modu": getattr(ai_engine, "RETRIEVAL_MODE", "similarity"),
            "zaman": datetime.now().isoformat(timespec="seconds"),
        }
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"  → {sinif}  (kaynak getirildi: {kaynak_getirildi})")


# ═════════════════════════════════════════════════════════════
#  AŞAMA 3: Rapor
# ═════════════════════════════════════════════════════════════
MANUAL_MARKER = "<!-- MANUEL BÖLÜM: bu satırın altı rapor yeniden üretilirken korunur -->"


def pct(a: int, b: int) -> str:
    return f"%{100 * a / b:.1f}" if b else "—"


def md_cell(s: str, n: int = 600) -> str:
    s = (s or "").replace("\r", "")
    s = s if len(s) <= n else s[:n] + " […]"
    return s.replace("\n", " ").replace("|", "\\|")


def write_report(questions: list[dict]) -> None:
    rows = [json.loads(l) for l in RESULTS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    qids = [q["id"] for q in questions]
    rows = sorted([r for r in rows if r["id"] in qids], key=lambda r: qids.index(r["id"]))
    ok_rows = [r for r in rows if r["sinif"] in LABELS]
    errs = [r for r in rows if r["sinif"] not in LABELS]
    N = len(ok_rows)
    c = {lab: sum(r["sinif"] == lab for r in ok_rows) for lab in LABELS}
    ans = [r for r in ok_rows if r["tur"] == "cevapli"]
    una = [r for r in ok_rows if r["tur"] == "cevapsiz"]
    halu_alt = {}
    for r in ok_rows:
        if r["sinif"] == "HALÜSİNASYON":
            halu_alt[r.get("hata_alt_tipi") or "belirtilmemiş"] = halu_alt.get(r.get("hata_alt_tipi") or "belirtilmemiş", 0) + 1

    # Retrieval teşhisi: cevaplı sorularda kaynak chunk bağlama girdi mi?
    ret_hit = [r for r in ans if r.get("kaynak_chunk_getirildi")]
    gr = [r for r in ans if r["sinif"] == "GEREKSİZ RET"]
    gr_miss = [r for r in gr if not r.get("kaynak_chunk_getirildi")]

    # Heuristik fallback dedektörü vs hakem
    def is_ret(lab):
        return lab in ("DOĞRU RET", "GEREKSİZ RET")
    agree = sum(r["heuristik_fallback"] == is_ret(r["sinif"]) for r in ok_rows)

    meta = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["meta"]
    gs = git_state()
    dates = sorted(r["zaman"] for r in rows)
    old = REPORT_FILE.read_text(encoding="utf-8") if REPORT_FILE.exists() else ""
    manual = old.split(MANUAL_MARKER, 1)[1] if MANUAL_MARKER in old else "\n\n## Gereksiz retleri azaltmak için öneriler\n\n_(henüz yazılmadı)_\n"

    L = []
    L.append("# Erasmus++ — Değerlendirme v2 Raporu\n")
    L.append("> Bu rapor `python eval_v2.py report` ile `eval_v2_results.jsonl` dosyasından otomatik üretildi. "
             "En alttaki öneriler bölümü elle yazıldı.\n")
    L.append("## Özet\n")
    L.append("| Metrik | Değer |\n|---|---|")
    L.append(f"| **Genel doğruluk** — (doğru cevap + doğru ret) / toplam | **{pct(c['DOĞRU CEVAP'] + c['DOĞRU RET'], N)}** ({c['DOĞRU CEVAP'] + c['DOĞRU RET']}/{N}) |")
    L.append(f"| **Halüsinasyon oranı** — halüsinasyon / toplam | **{pct(c['HALÜSİNASYON'], N)}** ({c['HALÜSİNASYON']}/{N}) |")
    L.append(f"| **Gereksiz ret oranı** — gereksiz ret / toplam | **{pct(c['GEREKSİZ RET'], N)}** ({c['GEREKSİZ RET']}/{N}) |")
    L.append(f"| Cevaplı sorularda doğru cevap | {pct(c['DOĞRU CEVAP'], len(ans))} ({c['DOĞRU CEVAP']}/{len(ans)}) |")
    L.append(f"| Cevaplı sorularda gereksiz ret | {pct(sum(r['sinif']=='GEREKSİZ RET' for r in ans), len(ans))} ({sum(r['sinif']=='GEREKSİZ RET' for r in ans)}/{len(ans)}) |")
    L.append(f"| Cevaplı sorularda halüsinasyon | {pct(sum(r['sinif']=='HALÜSİNASYON' for r in ans), len(ans))} ({sum(r['sinif']=='HALÜSİNASYON' for r in ans)}/{len(ans)}) |")
    L.append(f"| Cevapsız sorularda doğru ret | {pct(c['DOĞRU RET'], len(una))} ({c['DOĞRU RET']}/{len(una)}) |")
    L.append(f"| Cevapsız sorularda halüsinasyon | {pct(sum(r['sinif']=='HALÜSİNASYON' for r in una), len(una))} ({sum(r['sinif']=='HALÜSİNASYON' for r in una)}/{len(una)}) |")
    if errs:
        L.append(f"| Metrik dışı bırakılan (teknik hata) | {len(errs)} soru |")
    L.append("")
    L.append("### Sınıf dağılımı\n")
    L.append("| Sınıf | Cevaplı (n={}) | Cevapsız (n={}) | Toplam |\n|---|---|---|---|".format(len(ans), len(una)))
    for lab in LABELS:
        L.append(f"| {lab} | {sum(r['sinif']==lab for r in ans)} | {sum(r['sinif']==lab for r in una)} | {c[lab]} |")
    if halu_alt:
        L.append("\nHalüsinasyon alt tipleri: " + ", ".join(f"{k}: {v}" for k, v in sorted(halu_alt.items())))
    L.append("")

    L.append("## Kurulum ve tekrarlanabilirlik\n")
    L.append("| | |\n|---|---|")
    L.append(f"| Cevap veren model (bot) | `{ANSWER_MODEL}` (Groq, temperature=0) |")
    L.append(f"| Hakem modeli | `{JUDGE_MODEL}` (Groq, temperature=0, seed={SEED}) — bottan farklı model ailesi (Alibaba Qwen vs OpenAI gpt-oss) |")
    L.append(f"| Soru üretim modeli | `{meta.get('uretici_model')}` |")
    modes = sorted({r.get("retrieval_modu", "similarity") for r in rows})
    L.append(f"| Embedding / retrieval | OpenAI `text-embedding-3-small`, FAISS, k={getattr(ai_engine, 'MAIN_K', 5)} + konu boost (k=4), mod: `{', '.join(modes)}` |")
    L.append(f"| Koşu adı | `{EVAL_RUN or 'baseline'}` |")
    L.append(f"| Değerlendirme tarihi | {dates[0][:16].replace('T', ' ')} → {dates[-1][:16].replace('T', ' ')} |" if dates else "| Tarih | — |")
    L.append(f"| Soru seti oluşturma | {meta.get('olusturma_tarihi', '?').replace('T', ' ')} (seed={meta.get('seed')}) |")
    L.append(f"| Git commit | `{gs['commit']}`" + (" + **commit edilmemiş `ai_engine.py` değişikliği** (model `GROQ_MODEL` env değişkeninden okunuyor, varsayılan gpt-oss-120b)" if gs["ai_engine_degisiklik_var"] else "") + " |")
    L.append(f"| FAISS index (`index.faiss` md5) | `{meta.get('faiss_index_md5')}` |")
    L.append(f"| Soru sayısı | {len(questions)} ({sum(q['tur']=='cevapli' for q in questions)} cevaplı + {sum(q['tur']=='cevapsiz' for q in questions)} cevapsız = %{100*sum(q['tur']=='cevapsiz' for q in questions)/len(questions):.0f}) |")
    L.append("")
    L.append("Yeniden çalıştırmak için: `eval_v2_results.jsonl` dosyasını silip `python eval_v2.py run` ve ardından `python eval_v2.py report`. "
             "Soru seti `eval_v2_questions.json` içinde donduruldu; yeniden üretilmez. "
             "LLM'ler temperature=0'da bile Groq'ta birebir deterministik değildir; tekrar koşularda birkaç soruluk sapma beklenebilir.\n")

    L.append("## Teşhis\n")
    L.append(f"- **Retrieval isabeti:** Cevaplı {len(ans)} sorunun {len(ret_hit)} tanesinde ({pct(len(ret_hit), len(ans))}) sorunun üretildiği kaynak chunk, botun gördüğü bağlama girdi.")
    if gr:
        L.append(f"- Gereksiz retlerin {len(gr_miss)}/{len(gr)} tanesinde kaynak chunk bağlamda **yoktu** (retrieval hatası); "
                 f"{len(gr) - len(gr_miss)}/{len(gr)} tanesinde bağlamda olduğu hâlde model reddetti (prompt/okuma hatası).")
    L.append(f"- **Hakem ↔ anahtar kelime dedektörü uyumu:** `test_ai.py` tarzı fallback dedektörü ile hakemin ret/ret-değil kararı {agree}/{N} soruda ({pct(agree, N)}) örtüşüyor.")
    L.append("")

    fails = [r for r in rows if r["sinif"] not in ("DOĞRU CEVAP", "DOĞRU RET")]
    L.append(f"## Başarısız örnekler ({len(fails)})\n")
    for r in fails:
        src = f"{r['kaynak_dosya']} — s.{r['sayfa']}" if r["kaynak_dosya"] else "— (belgelerde cevap yok)"
        alt = f" / {r['hata_alt_tipi']}" if r.get("hata_alt_tipi") else ""
        L.append(f"### {r['id']} — {r['sinif']}{alt}\n")
        L.append(f"- **Soru:** {r['soru']}")
        L.append(f"- **Beklenen cevap:** {md_cell(r['beklenen_cevap'], 400)}")
        L.append(f"- **Kaynak:** {src}")
        if r["tur"] == "cevapli":
            L.append(f"- **Kaynak chunk bağlamda mıydı:** {'evet' if r.get('kaynak_chunk_getirildi') else 'hayır'}")
        L.append(f"- **Bot cevabı:** {md_cell(r['bot_cevabi'], 700)}")
        L.append(f"- **Hata nedeni (hakem):** {md_cell(r['hakem_gerekce'], 400)}")
        L.append("")

    L.append("## Tüm sonuçlar\n")
    L.append("| ID | Tür | Sınıf | Kaynak bağlamda | Soru |\n|---|---|---|---|---|")
    for r in rows:
        kb = "—" if r["tur"] == "cevapsiz" else ("✓" if r.get("kaynak_chunk_getirildi") else "✗")
        L.append(f"| {r['id']} | {r['tur']} | {r['sinif']} | {kb} | {md_cell(r['soru'], 140)} |")
    L.append("")
    L.append(MANUAL_MARKER + manual.rstrip() + "\n")

    REPORT_FILE.write_text("\n".join(L), encoding="utf-8")
    log(f"Rapor yazıldı: {REPORT_FILE.name}")
    log(f"Genel doğruluk {pct(c['DOĞRU CEVAP'] + c['DOĞRU RET'], N)} | Halüsinasyon {pct(c['HALÜSİNASYON'], N)} | Gereksiz ret {pct(c['GEREKSİZ RET'], N)}")


# ═════════════════════════════════════════════════════════════
async def main():
    if JUDGE_MODEL == ANSWER_MODEL:
        sys.exit(f"HATA: Hakem modeli cevap veren modelle aynı olamaz ({JUDGE_MODEL}).")
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    log(f"Cevap modeli: {ANSWER_MODEL} | Hakem: {JUDGE_MODEL} | Soru üretici: {GEN_MODEL}")
    if stage in ("generate", "all"):
        await generate_questions()
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    if stage in ("run", "all"):
        await run_eval(questions)
    if stage in ("report", "all"):
        write_report(questions)


if __name__ == "__main__":
    asyncio.run(main())
