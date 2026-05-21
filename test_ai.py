"""
Erasmus AI Mentorluk Projesi -- RAG Regresyon Test Paketi
========================================================
test_cases.json icerisindeki senaryolari ai_engine.py uzerinden
otonom olarak calistirir ve sonuclari dogrular.

Test Mantigi:
  - Cevapta beklenen kelimeler varsa      -> PASSED (dogru bilgi)
  - Cevapta yasakli kelimeler varsa       -> FAILED (halusinasyon!)
  - Cevap fallback ise ve fallback_kabul  -> PASSED (guvenli ret)
  - Cevap fallback ise ve fallback_kabul degil -> FAILED (bilgi olmali)

Kullanim:
    python test_ai.py          (standart calistirma)
    python test_ai.py -v       (detayli ciktili)
"""

import sys
import os
import json
import asyncio
import unittest

# Windows terminal UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ai_engine import get_ai_response

# ──────────────────────────────────────
#  Test case dosyasini yukle
# ──────────────────────────────────────
TEST_CASES_FILE = os.path.join(os.path.dirname(__file__), "test_cases.json")

with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
    TEST_CASES = json.load(f)


FALLBACK_MARKERS = [
    "rehberde yok",
    "koordinatör",
    "teyit etmen lazım",
    "teyit etmen laz",
    "elimdeki resmi",
    "bilgi yok",
]


def _is_fallback(cevap: str) -> bool:
    """Cevabin fallback/bilmiyorum yaniti olup olmadigini kontrol et."""
    lower = cevap.lower()
    return any(marker in lower for marker in FALLBACK_MARKERS)


# ──────────────────────────────────────
#  Test Sinifi
# ──────────────────────────────────────
class TestErasmusRAG(unittest.TestCase):
    """ai_engine.py uzerinden RAG dogruluk testleri."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.loop = asyncio.get_event_loop()
            if cls.loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            cls.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls.loop)

    def _ask(self, question: str) -> str:
        uid = hash(question) % 100000
        return self.loop.run_until_complete(
            get_ai_response(question, user_id=uid)
        )


def _make_test(case):
    """Bir test_case dict'inden unittest metodu uretir."""

    def test_method(self):
        soru = case["soru"]
        beklenen = case.get("beklenen_kelimeler", [])
        yasakli = case.get("yasakli_kelimeler", [])
        fallback_kabul = case.get("fallback_kabul", False)
        test_id = case["id"]
        aciklama = case.get("aciklama", "")

        print(f"\n{'='*60}")
        print(f"  TEST: {test_id}")
        print(f"  Soru: {soru}")
        print(f"  Tur : {case.get('test_turu', '?')}")
        print(f"  Not : {aciklama}")
        print(f"{'='*60}")

        # LLM'e sor
        cevap = self._ask(soru)
        cevap_lower = cevap.lower()

        print(f"\n  LLM Cevabi:\n  {cevap}\n")

        # ── ADIM 1: Yasakli kelime kontrolu (halusinasyon tespiti) ──
        bulunan_yasak = [kw for kw in yasakli if kw.lower() in cevap_lower]
        if bulunan_yasak:
            self.fail(
                f"[{test_id}] HALUSUNASYON! Yasakli kelimeler cevapta bulundu: "
                f"{bulunan_yasak}\n  Cevap: {cevap[:300]}"
            )

        # ── ADIM 2: Fallback kontrolu ──
        is_fb = _is_fallback(cevap)
        test_turu = case.get("test_turu", "")

        if is_fb:
            if fallback_kabul or test_turu == "fallback":
                print(f"  >> PASSED (guvenli fallback -- halusinasyon yok)")
                return  # Test gecti
            else:
                self.fail(
                    f"[{test_id}] FAILED -- Fallback verildi ama bu soruda "
                    f"kesin cevap bekleniyordu.\n  Cevap: {cevap[:300]}"
                )

        # fallback turundeki test icin: fallback vermedi ama yanlis icerik de yok
        if test_turu == "fallback" and not is_fb:
            self.fail(
                f"[{test_id}] FAILED -- Fallback turu testte cevap verildi, "
                f"fallback bekleniyordu.\n  Cevap: {cevap[:300]}"
            )

        # ── ADIM 3: Beklenen kelime kontrolu ──
        eksik = [kw for kw in beklenen if kw.lower() not in cevap_lower]
        if eksik:
            self.fail(
                f"[{test_id}] FAILED -- Beklenen kelimeler cevapta "
                f"bulunamadi: {eksik}\n  Cevap: {cevap[:300]}"
            )

        print(f"  >> PASSED (dogru bilgi)")

    test_method.__doc__ = f"{case['id']}: {case.get('aciklama', case['soru'])}"
    return test_method


# Dinamik test metod uretimi
for i, case in enumerate(TEST_CASES):
    method_name = f"test_{i+1:02d}_{case['id']}"
    setattr(TestErasmusRAG, method_name, _make_test(case))


# ──────────────────────────────────────
#  Ana calistirma
# ──────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ERASMUS AI -- RAG REGRESYON TEST PAKETI")
    print(f"  Toplam senaryo: {len(TEST_CASES)}")
    print("  Mantik: Halusinasyon = FAIL | Fallback = kabul edilebilir")
    print("="*60)

    unittest.main(verbosity=2)
