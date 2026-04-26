import os
from langchain_community.document_loaders import PyPDFDirectoryLoader, DirectoryLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY bulunamadı! Lütfen .env dosyasını kontrol edin.")

def build_vector_database():
    input_directory = "./info_bank"
    output_directory = "./faiss_index"

    if not os.path.exists(input_directory):
        print(f"Hata: '{input_directory}' klasörü bulunamadı.")
        return

    print("1. PDF dosyaları yükleniyor...")
    pdf_loader = PyPDFDirectoryLoader(input_directory)
    pdf_documents = pdf_loader.load()
    print(f"   -> {len(pdf_documents)} sayfa PDF okundu.")

    print("2. Word (.docx) dosyaları yükleniyor...")
    word_loader = DirectoryLoader(input_directory, glob="**/*.docx", loader_cls=Docx2txtLoader)
    word_documents = word_loader.load()
    print(f"   -> {len(word_documents)} adet Word belgesi okundu.")

    documents = pdf_documents + word_documents

    if not documents:
        print(f"Hata: '{input_directory}' klasöründe PDF veya Word dosyası bulunamadı.")
        return

    print(f"Toplam {len(documents)} belge birleştirildi.")

    print("3. Metinler uygun parçalara bölünüyor...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Toplam {len(chunks)} adet metin parçası (chunk) oluşturuldu.")

    print("4. OpenAI ile embedding işlemleri yapılıyor...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    print("5. FAISS veritabanı oluşturuluyor ve kaydediliyor...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(output_directory)

    print(f"İşlem tamamlandı! Vektör veritabanı '{output_directory}' klasörüne başarıyla kaydedildi.")

if __name__ == "__main__":
    build_vector_database()
