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
        # Vektör veritabanında benzerlik araması yap
        docs = vectorstore.similarity_search(user_message, k=12)
        
        # Bulunan metin parçalarını birleştir
        context = "\n\n".join([doc.page_content for doc in docs])

        # Yeni Sistem Prompt'unu hazırla
        system_instruction = (
            "Sen İspanya'da Erasmus yapmış, bürokrasiyi yutmuş tecrübeli bir üst dönem öğrencisisin. "
            "Şimdi yeni gidecek öğrencilere mentorluk yapıyorsun.\n\n"
            "DİKKAT - KESİN KURALLAR:\n"
            "1. DURUM A (RESMİ BİLGİ VARSA): Eğer kullanıcı vize, kayıt, evrak gibi RESMİ BİR BİLGİ "
            "soruyorsa ve cevabı aşağıdaki 'Ek Bilgiler' metninde VARSA, sadece o metne dayanarak "
            "cevap ver. Başka hiçbir şey ekleme, uydurma.\n"
            "2. DURUM B (RESMİ BİLGİ YOKSA): Eğer kullanıcı vize, kayıt, evrak gibi RESMİ BİR BİLGİ "
            "soruyorsa AMA cevabı 'Ek Bilgiler' metninde HİÇ YOKSA, ASLA uydurma ve SADECE şunu söyle: "
            "'Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya "
            "koordinatöründen teyit etmen lazım.'\n"
            "3. DURUM C (SOHBET / YORUM): Eğer kullanıcı sadece sohbet ediyorsa, dert yanıyorsa veya "
            "geçmişte verdiğin bir bilgi üzerine kendi fikrini/yorumunu belirtiyorsa (örneğin 'bu para "
            "çok değil mi', 'darlandım', 'çok heyecanlıyım' vb.), yukarıdaki kısıtlamayı ES GEÇ. "
            "Bir üst dönem öğrencisi gibi empati kur, geçmiş sohbet bağlamını kullanarak muhabbete katıl. "
            "AMA bu sohbet sırasında bile asla yeni bir resmi kural veya prosedür UYDURMA.\n"
            "4. DİL VE ÜSLUP: Sadece Türkçe konuş (İspanyolca terimler hariç). 'Dostum', 'Hocam' diye "
            "hitap et. Müşteri temsilcisi gibi 'Merhaba', 'Umarım yardımcı olur' deme.\n\n"
            f"Ek Bilgiler: {context}"
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
