import os
import datetime
from groq import AsyncGroq
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY bulunamadı! Lütfen .env dosyasını kontrol edin.")

client = AsyncGroq(api_key=GROQ_API_KEY)

# FAISS Vektör veritabanını belleğe yükle
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = FAISS.load_local(
    "./faiss_index",
    embeddings,
    allow_dangerous_deserialization=True
)


# Kullanıcı bazlı kısa süreli hafıza (Sliding Window)
user_sessions = {}

async def get_ai_response(user_message: str, user_id: int) -> str:
    try:
        # ── Hibrit Arama (Hybrid Retrieval) ──
        # 1) Ana semantik arama: kullanıcının tam sorusu
        docs_main = vectorstore.similarity_search(user_message, k=5)

        # 2) Anahtar kelime odaklı ek arama: hibe, ücret, maaş gibi
        #    finansal terimler tespit edilirse özel bir sorgu daha yapılır
        financial_keywords = [
            "hibe", "ücret", "maaş", "para", "avro", "euro",
            "burs", "ödeme", "maliyet", "masraf", "seyahat desteği"
        ]
        msg_lower = user_message.lower()
        has_financial = any(kw in msg_lower for kw in financial_keywords)

        if has_financial:
            boost_query = "erasmus hibe miktarı aylık ücret avro euro seyahat desteği"
            docs_boost = vectorstore.similarity_search(boost_query, k=4)
        else:
            docs_boost = []

        # 3) Birleştir ve tekrar edenleri çıkar (deduplicate)
        seen_ids = set()
        docs = []
        for doc in docs_main + docs_boost:
            doc_id = f"{doc.metadata.get('source', '')}_{doc.metadata.get('page', '')}_{doc.page_content[:80]}"
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                docs.append(doc)

        # Bulunan metin parçalarını kaynak etiketleriyle birleştir
        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Bilinmiyor")
            page = doc.metadata.get("page", "?")
            context_parts.append(
                f"[Kaynak {i} | Dosya: {source} | Sayfa: {page}]\n{doc.page_content}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # Katı Sistem Prompt'u — Halüsinasyon Önleme
        system_instruction = (
            "Sen İspanya'da Erasmus yapmış, bürokrasiyi yutmuş tecrübeli bir üst dönem öğrencisisin. "
            "Şimdi yeni gidecek öğrencilere mentorluk yapıyorsun.\n\n"
            "═══════════════════════════════════════\n"
            "KESİN KURALLAR (İHLAL ETME!)\n"
            "═══════════════════════════════════════\n\n"
            "KURAL 1 — TEK DOĞRU KAYNAK: Aşağıdaki [KAYNAK METİNLER] bölümü, sana verilen resmi Erasmus belgelerinden "
            "çekilmiş bilgilerdir. Bir soruyu cevaplarken SADECE ve SADECE bu kaynak metinlerdeki bilgileri kullan. "
            "Kendi genel kültüründen, eğitim verilerinden veya ezberinden ASLA bir rakam, tarih, ücret veya prosedür UYDURMA. "
            "Örneğin kaynaklarda '600 Avro' yazıyorsa '600 Avro' de; '850 Avro' veya başka bir rakam UYDURMA.\n\n"
            "KURAL 2 — BİLGİ VARSA: Eğer kullanıcının sorusunun cevabı [KAYNAK METİNLER] içinde net olarak varsa "
            "(rakam, tarih, prosedür, tablo verisi), o bilgiyi aynen ve sadık kalarak kullan. "
            "Kaynağı kendiliğinden genişletme veya yorumlama.\n\n"
            "KURAL 3 — BİLGİ YOKSA: Eğer kullanıcının sorusunun cevabı [KAYNAK METİNLER] içinde HİÇ YOKSA, "
            "ASLA uydurma. SADECE şunu söyle: "
            "'Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya "
            "koordinatöründen teyit etmen lazım.'\n\n"
            "KURAL 4 — SOHBET / YORUM: Eğer kullanıcı sadece sohbet ediyorsa, dert yanıyorsa veya "
            "yorum yapıyorsa (örneğin 'bu para çok değil mi', 'darlandım', 'çok heyecanlıyım'), "
            "bir üst dönem öğrencisi gibi empati kur ve muhabbete katıl. "
            "AMA sohbet sırasında bile asla yeni bir resmi kural veya prosedür UYDURMA.\n\n"
            "KURAL 5 — DİL VE ÜSLUP: Sadece Türkçe konuş (İspanyolca terimler hariç). 'Dostum', 'Hocam' diye "
            "hitap et. Müşteri temsilcisi gibi 'Merhaba', 'Umarım yardımcı olur' gibi kalıplar KULLANMA.\n\n"
            "═══════════════════════════════════════\n"
            "[KAYNAK METİNLER]\n"
            "═══════════════════════════════════════\n\n"
            f"{context}\n\n"
            "═══════════════════════════════════════\n"
            "[KAYNAK METİNLER SONU]\n"
            "═══════════════════════════════════════"
        )

        # Kullanıcının geçmiş mesajlarını al (yoksa boş liste oluştur)
        if user_id not in user_sessions:
            user_sessions[user_id] = []

        # Messages listesini oluştur: System + Geçmiş + Yeni soru
        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(user_sessions[user_id])
        messages.append({"role": "user", "content": user_message})

        # Modele mesaj geçmişiyle birlikte gönder
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            messages=messages
        )
        ai_reply = response.choices[0].message.content

        # Son soru-cevap çiftini hafızaya kaydet
        user_sessions[user_id].append({"role": "user", "content": user_message})
        user_sessions[user_id].append({"role": "assistant", "content": ai_reply})

        # TOKEN KORUMASI: Sadece son 3 soru-cevap çiftini (6 mesaj) tut
        if len(user_sessions[user_id]) > 6:
            user_sessions[user_id] = user_sessions[user_id][-6:]

        # Cevaplanamayan soruları logla
        if "elimdeki resmi rehberde yok" in ai_reply:
            with open("eksik_sorular.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] - Soru: {user_message}\n")

        return ai_reply
    except Exception as e:
        print(f"Groq API Hatası: {e}")
        return "Şu anda teknik bir aksaklık yaşıyorum. Lütfen daha sonra tekrar dene."
