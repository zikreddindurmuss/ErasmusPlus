import os
import datetime
from groq import AsyncGroq
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

import memory_store

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Groq üzerinde çalışan model. Groq bir modeli kaldırdığında (llama-3.3-70b-versatile
# kaldırıldı ve 404 dönüyordu) kod değiştirmeden .env içinden GROQ_MODEL ile değiştirilebilir.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

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

# Kullanıcı bazlı kısa süreli hafıza (Sliding Window) — kalıcı SQLite katmanı
memory_store.init_db()


# ── Retrieval ayarları ──
# "mmr_cap" (varsayılan): MMR ile çeşitlendirilmiş geniş aday havuzundan,
#   her kaynak dosyadan en fazla MAX_PER_SOURCE chunk alınır. Tek bir büyük
#   belgenin (ör. 174 chunk'lık "Veri Seti" PDF'i) top-k'yi doldurup asıl
#   kaynağı dışarıda bırakmasını önler (eval_v2: başarısız 15 örneğin 14'ü).
# "similarity": eski davranış (saf benzerlik, sınır yok). Geri dönüş ve
#   karşılaştırma için .env içinden RETRIEVAL_MODE=similarity ile açılabilir.
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "mmr_cap")
MAX_PER_SOURCE = 2
MMR_FETCH_K = 30       # MMR'ın seçeceği aday sayısı
MMR_LAMBDA = 0.7       # 1.0 = saf benzerlik, 0.0 = saf çeşitlilik


def _retrieve(query: str, k: int, university: str | None = None):
    """
    FAISS semantik arama — opsiyonel `university` metadata filtresiyle.
    Çok-üniversiteli yapıya hazırlık: university verilirse yalnızca o
    üniversitenin chunk'ları döner. university=None iken filtre uygulanmaz.
    """
    flt = {"university": university} if university else None
    if RETRIEVAL_MODE == "similarity":
        return vectorstore.similarity_search(query, k=k, filter=flt)

    candidates = vectorstore.max_marginal_relevance_search(
        query, k=MMR_FETCH_K, fetch_k=MMR_FETCH_K * 2,
        lambda_mult=MMR_LAMBDA, filter=flt,
    )
    out, per_source = [], {}
    for doc in candidates:
        src = doc.metadata.get("source")
        if per_source.get(src, 0) >= MAX_PER_SOURCE:
            continue
        out.append(doc)
        per_source[src] = per_source.get(src, 0) + 1
        if len(out) == k:
            break
    return out


# ── Konu-odaklı Boost Yapılandırması ──
# Kullanıcının mesajında bir konunun anahtar kelimelerinden herhangi biri
# geçerse, o konunun `boost_query`'si için ek bir semantik arama yapılır.
# Veri-odaklı ve genişletilebilir: yeni konu eklemek için buraya bir giriş
# eklemek yeterli (kod değişikliği gerekmez).
BOOST_TOPICS = {
    "finans": {
        "keywords": [
            "hibe", "ücret", "maaş", "para", "avro", "euro",
            "burs", "ödeme", "maliyet", "masraf", "seyahat desteği",
        ],
        "boost_query": "erasmus hibe miktarı aylık ücret avro euro seyahat desteği",
    },
    "vize": {
        "keywords": [
            "vize", "oturum", "ikamet", "tie", "nie", "konsolosluk", "randevu",
        ],
        "boost_query": "vize oturum izni ikamet tie nie başvuru randevu konsolosluk",
    },
    "konaklama": {
        # Not: kısa/genel kelimelerden (ör. "ev") kaçınılır — substring
        # eşleşmesi "randevu", "evrak" gibi alakasız kelimeleri yakalar.
        "keywords": [
            "konaklama", "yurt", "kira", "daire", "residencia", "konut", "kiralık",
        ],
        "boost_query": "konaklama yurt ev kiralama residencia aylık kira",
    },
    "ola": {
        "keywords": [
            "ders", "ola", "learning agreement", "öğrenim anlaşması",
            "kredi", "ects", "ders seçimi",
        ],
        "boost_query": "ders seçimi learning agreement öğrenim anlaşması ects kredi",
    },
    "umove": {
        # Not: "kayıt" gibi geniş kelimeler bilinçli olarak dışarıda bırakıldı —
        # substring eşleşmesi "adli sicil kaydı", "ders kaydı" gibi alakasız
        # sorulara sıçrar; "matricula" aksansız form, aksanlı yazımı ("matrícula")
        # da ayrıca kapsansın diye iki ayrı kelime olarak var.
        "keywords": [
            "umove", "matrícula", "matricula", "empadronamiento",
        ],
        "boost_query": "UMOVE platformuna sigorta poliçesi yükleme UJA kayıt",
    },
    "staj": {
        "keywords": [
            "staj", "práctica", "practica", "traineeship", "internship",
        ],
        "boost_query": "Erasmus Faaliyeti ile İlgili Diğer Kurallar toplam süre sınırlaması 12 ay hibe öğrenim hareketliliği staj hareketliliği",
    },
}

# Her eşleşen konu için çekilecek ek chunk sayısı (eski finansal boost ile aynı)
BOOST_K = 4
# Ana semantik aramada çekilecek chunk sayısı
MAIN_K = 5


def retrieve_context(user_message: str, university: str | None = None) -> list:
    """
    Botun cevap üretirken gördüğü belge parçalarını döndürür.
    get_ai_response ve değerlendirme scripti (eval_v2.py) aynı fonksiyonu
    kullanır; böylece hakem, botun gerçekten gördüğü bağlamı görür.
    """
    # ── Hibrit Arama (Hybrid Retrieval) ──
    # 1) Ana semantik arama: kullanıcının tam sorusu
    docs_main = _retrieve(user_message, MAIN_K, university)

    # 2) Konu-odaklı ek arama (Boost): mesajda bir konunun anahtar
    #    kelimelerinden biri geçiyorsa, o konunun sorgusu için ek chunk'lar
    #    çekilir. Veri-odaklı — konular BOOST_TOPICS'te tanımlıdır.
    msg_lower = user_message.lower()
    docs_boost = []
    for topic in BOOST_TOPICS.values():
        if any(kw in msg_lower for kw in topic["keywords"]):
            docs_boost.extend(_retrieve(topic["boost_query"], BOOST_K, university))

    # 3) Birleştir ve tekrar edenleri çıkar (deduplicate)
    seen_ids = set()
    docs = []
    for doc in docs_main + docs_boost:
        doc_id = f"{doc.metadata.get('source', '')}_{doc.metadata.get('page', '')}_{doc.page_content[:80]}"
        if doc_id not in seen_ids:
            seen_ids.add(doc_id)
            docs.append(doc)
    return docs


async def get_ai_response(user_message: str, user_id: int, university: str | None = None) -> str:
    try:
        docs = retrieve_context(user_message, university)

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

        # Kullanıcının geçmiş mesajlarını kalıcı hafızadan al (son 6 mesaj)
        history = memory_store.get_history(user_id)

        # Messages listesini oluştur: System + Geçmiş + Yeni soru
        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # Modele mesaj geçmişiyle birlikte gönder
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.0,
            messages=messages
        )
        ai_reply = response.choices[0].message.content

        # Son soru-cevap çiftini kalıcı hafızaya kaydet.
        # add_turn ayrıca sliding window'u (son 3 soru-cevap = 6 mesaj) uygular.
        memory_store.add_turn(user_id, user_message, ai_reply)

        # Cevaplanamayan soruları logla
        if "elimdeki resmi rehberde yok" in ai_reply:
            with open("eksik_sorular.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}] - Soru: {user_message}\n")

        return ai_reply
    except Exception as e:
        print(f"Groq API Hatası: {e}")
        return "Şu anda teknik bir aksaklık yaşıyorum. Lütfen daha sonra tekrar dene."
