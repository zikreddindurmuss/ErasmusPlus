import os
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

def build_vector_database():
    input_directory = "./info_bank"
    output_directory = "./faiss_index"

    if not os.path.exists(input_directory):
        print(f"Hata: '{input_directory}' klasörü bulunamadı.")
        return

    print("1. PDF dosyaları yükleniyor...")
    loader = PyPDFDirectoryLoader(input_directory)
    documents = loader.load()
    
    if not documents:
        print(f"Hata: '{input_directory}' klasöründe PDF dosyası bulunamadı.")
        return
        
    print(f"Toplam {len(documents)} sayfa belge okundu.")

    print("2. Metinler uygun parçalara bölünüyor...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Toplam {len(chunks)} adet metin parçası (chunk) oluşturuldu.")

    print("3. HuggingFace ile embedding işlemleri yapılıyor...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    print("4. FAISS veritabanı oluşturuluyor ve kaydediliyor...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(output_directory)

    print(f"İşlem tamamlandı! Vektör veritabanı '{output_directory}' klasörüne başarıyla kaydedildi.")

if __name__ == "__main__":
    build_vector_database()
