import os
from groq import AsyncGroq
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY bulunamadı! Lütfen .env dosyasını kontrol edin.")

client = AsyncGroq(api_key=GROQ_API_KEY)

# FAISS Vektör veritabanını belleğe yükle
vectorstore = FAISS.load_local(
    "./faiss_index", 
    HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2"), 
    allow_dangerous_deserialization=True
)

async def get_ai_response(user_message: str) -> str:
    try:
        # Vektör veritabanında benzerlik araması yap
        docs = vectorstore.similarity_search(user_message, k=3)
        
        # Bulunan metin parçalarını birleştir
        context = "\n\n".join([doc.page_content for doc in docs])

        # Yeni Sistem Prompt'unu hazırla
        system_instruction = (
            "Sen Erasmus öğrencilerine rehberlik eden disiplinli bir mentorsun. "
            "Sana sorulan soruyu SADECE şu 'Ek Bilgiler' metnine dayanarak yanıtla. "
            "Eğer bilgi metinde yoksa 'Bu konuda elimde resmi veri yok' de. "
            f"Ek Bilgiler: {context}"
        )

        # Modele sadece ilgili context'i gönder
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq API Hatası: {e}")
        return "Şu anda teknik bir aksaklık yaşıyorum. Lütfen daha sonra tekrar dene."
