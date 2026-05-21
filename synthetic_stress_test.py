import os
import sys
import json
import time
import random
import asyncio
from pathlib import Path
from tqdm import tqdm

# Windows terminal UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from langchain_ollama import OllamaLLM
from ai_engine import get_ai_response

# ═════════════════════════════════════════════════════════════
#  AYARLAR
# ═════════════════════════════════════════════════════════════
OLLAMA_MODEL = "qwen2.5:3b"
TARGET_QUESTION_COUNT = 30
CACHE_DIR = Path(".chunk_cache")
TEMP_DATA_FILE = Path("synthetic_questions_temp.json")
LOG_FILE = Path("sentetik_test1.txt")

try:
    llm = OllamaLLM(model=OLLAMA_MODEL, temperature=0.2)
except Exception as e:
    print(f"Ollama başlatılamadı: {e}")
    sys.exit(1)


# ═════════════════════════════════════════════════════════════
#  AŞAMA 1: Soru Üretimi (Sentetik Veri)
# ═════════════════════════════════════════════════════════════
def load_all_chunks():
    chunks = []
    if not CACHE_DIR.exists():
        print("HATA: .chunk_cache klasörü bulunamadı!")
        return chunks
        
    for p in CACHE_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    text = item.get("text", "").strip()
                    if len(text) > 200: # Yeterli bilgi içeren chunk'lar
                        chunks.append(item)
        except Exception:
            pass
    return chunks

def generate_synthetic_data():
    print("\n[AŞAMA 1] Soru Üretimi Başlıyor...")
    if TEMP_DATA_FILE.exists():
        print("Geçici dosya bulundu, sorular oradan yükleniyor...")
        with open(TEMP_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
            
    chunks = load_all_chunks()
    if not chunks:
        print("Hiç chunk bulunamadı!")
        return []
        
    random.shuffle(chunks)
    synthetic_data = []
    
    prompt_template = """Sen bir sınav hazırlama asistanısın. Aşağıda bir Erasmus bilgilendirme belgesinden alınmış bir metin (chunk) var. 
Lütfen SADECE VE SADECE BU METİNDE geçen spesifik bir bilgiye (rakam, kural, yer) dayanan 1 adet gerçekçi öğrenci sorusu üret. 
ÖNEMLİ KURALLAR:
1. Soru metnin içeriğiyle tam eşleşmeli. Metin vize hakkındaysa soru vize hakkında olmalı. Metin hibeyle ilgiliyse soru hibe hakkında olmalı.
2. Kesinlikle "Staj yapabilir miyim?" sorusunu KULLANMA. Orijinal ol.
3. Soru öğrenci ağzından sorulsun (Örn: "Sigortamı nasıl yaptırırım?", "Ders seçimimi ne zaman yapacağım?", "Yurtta kalmak zorunlu mu?").
4. Çıktı OLARAK SADECE SORUYU YAZ. Başka hiçbir kelime, numara veya açıklama ekleme.

Metin:
{text}
Soru:"""

    pbar = tqdm(total=TARGET_QUESTION_COUNT, desc="Soru Üretiliyor")
    
    for chunk in chunks:
        if len(synthetic_data) >= TARGET_QUESTION_COUNT:
            break
            
        text = chunk["text"]
        try:
            prompt = prompt_template.format(text=text)
            question = llm.invoke(prompt).strip()
            
            # Basit temizlik (bazen LLM 1., - vs koyabiliyor)
            question = question.lstrip("1234567890.-* ").strip()
            
            if "?" in question and len(question) > 10:
                synthetic_data.append({
                    "soru": question,
                    "kaynak": text
                })
                pbar.update(1)
        except Exception as e:
            continue

    pbar.close()
    
    # Geçici kaydet (ileride kaldığı yerden devam etmek isterse)
    with open(TEMP_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(synthetic_data, f, ensure_ascii=False, indent=2)
        
    print(f"Toplam {len(synthetic_data)} soru üretildi ve kaydedildi.")
    return synthetic_data


# ═════════════════════════════════════════════════════════════
#  AŞAMA 2: Otonom Test
# ═════════════════════════════════════════════════════════════
async def run_autonomous_tests(synthetic_data):
    print("\n[AŞAMA 2] Otonom Test Başlıyor...")
    
    for i, item in enumerate(tqdm(synthetic_data, desc="Bota Soruluyor")):
        if "bot_cevabi" in item:
            continue # Önceden alınmışsa atla
            
        soru = item["soru"]
        # API limitine takılmamak için bekleme süresini 3 saniyeye çıkardık
        await asyncio.sleep(3.0) 
        
        try:
            cevap = await get_ai_response(soru, user_id=1000 + i)
            item["bot_cevabi"] = cevap
        except Exception as e:
            item["bot_cevabi"] = f"HATA: {e}"
            
        # Her 10 soruda bir yedekle (API çökmesi vs durumunda veri kaybetmemek için)
        if (i + 1) % 10 == 0:
            with open(TEMP_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(synthetic_data, f, ensure_ascii=False, indent=2)

    with open(TEMP_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(synthetic_data, f, ensure_ascii=False, indent=2)
        
    return synthetic_data


# ═════════════════════════════════════════════════════════════
#  AŞAMA 3: Değerlendirme ve Loglama (LLM as a Judge)
# ═════════════════════════════════════════════════════════════
def evaluate_and_log(synthetic_data):
    print("\n[AŞAMA 3] Değerlendirme (LLM-as-a-Judge) Başlıyor...")
    
    judge_prompt = """Sen bir denetim hakemisin.
Öğrencinin sorusunu, asıl doğru bilginin bulunduğu kaynak metni ve yapay zeka botunun verdiği cevabı incele.

[Öğrencinin Sorusu]: {soru}
[Kaynak Metin]: {kaynak}
[Botun Cevabı]: {cevap}

GÖREV:
Botun cevabını değerlendir. YALNIZCA aşağıdaki üç etiketten BİRİNİ yaz (başka hiçbir açıklama yapma):
1) DOĞRU (Eğer bot bilgiyi doğru verdiyse veya güvenli bir şekilde reddettiyse)
2) GEREKSİZ FALLBACK (Eğer asıl bilgide cevap net olmasına rağmen bot "Bilmiyorum", "Rehberde yok", "Teyit etmen lazım" gibi bir cevap verdiyse)
3) HALÜSİNASYON (Eğer bot kaynak metinde olmayan yanlış bir rakam, tarih veya spesifik bilgi uydurduysa)

KARAR ETİKETİ:"""

    hata_sayisi = 0
    
    with open(LOG_FILE, "w", encoding="utf-8") as f_log:
        f_log.write("=== ERASMUS AI SENTETİK STRES TESTİ LOGLARI ===\n\n")
        
        for item in tqdm(synthetic_data, desc="Cevaplar Değerlendiriliyor"):
            soru = item["soru"]
            kaynak = item["kaynak"]
            cevap = item.get("bot_cevabi", "")
            
            prompt = judge_prompt.format(soru=soru, kaynak=kaynak, cevap=cevap)
            
            try:
                karar = llm.invoke(prompt).strip().upper()
            except Exception:
                karar = "HATA"
                
            is_error = False
            hata_turu = ""
            
            if "HALÜSİNASYON" in karar:
                is_error = True
                hata_turu = "Halüsinasyon (Uydurma/Yanlış Bilgi)"
            elif "GEREKSİZ FALLBACK" in karar:
                is_error = True
                hata_turu = "Gereksiz Fallback (Bilgi var ama bulunamadı)"
            elif "HATA" in karar:
                is_error = True
                hata_turu = "Değerlendirme Hatası"
                
            if is_error:
                hata_sayisi += 1
                log_text = (
                    f"----------------------------------------\n"
                    f"[SORU]: {soru}\n\n"
                    f"[BEKLENEN/KAYNAK BİLGİ]: {kaynak}\n\n"
                    f"[BOTUN CEVABI]: {cevap}\n\n"
                    f"[HATA TÜRÜ]: {hata_turu}\n"
                    f"----------------------------------------\n\n"
                )
                f_log.write(log_text)
                f_log.flush()

    print(f"\nDeğerlendirme bitti! Toplam {hata_sayisi} hata tespit edildi.")
    print(f"Hata logları '{LOG_FILE}' dosyasına kaydedildi.")


async def main():
    print(f"Hedef: {TARGET_QUESTION_COUNT} soru.")
    
    # 1. Aşama
    data = generate_synthetic_data()
    
    # 2. Aşama
    data = await run_autonomous_tests(data)
    
    # 3. Aşama
    evaluate_and_log(data)

if __name__ == "__main__":
    asyncio.run(main())
