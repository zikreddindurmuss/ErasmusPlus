import os
from pypdf import PdfReader

def extract_text_from_pdfs(input_folder: str, output_file: str):
    if not os.path.exists(input_folder):
        print(f"Hata: '{input_folder}' klasörü bulunamadı.")
        return

    extracted_text = []
    pdf_bulundu = False
    
    # Klasördeki dosyaları listele
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(".pdf"):
            pdf_bulundu = True
            pdf_path = os.path.join(input_folder, filename)
            print(f"Okunuyor: {filename}...")
            
            try:
                reader = PdfReader(pdf_path)
                extracted_text.append(f"--- {filename} İÇERİĞİ ---")
                
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        extracted_text.append(text)
                
                extracted_text.append("\n\n") # PDF'ler arası boşluk
            except Exception as e:
                print(f"'{filename}' okunurken hata oluştu: {e}")
                
    if not pdf_bulundu:
        print(f"'{input_folder}' klasöründe PDF dosyası bulunamadı.")
        return

    # Metni txt dosyasına yaz (UTF-8 encoding ile)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(extracted_text))
        print(f"İşlem tamamlandı! Bütün içerikler başarıyla '{output_file}' dosyasına kaydedildi.")
    except Exception as e:
        print(f"Dosyaya yazarken hata oluştu: {e}")

if __name__ == "__main__":
    INPUT_FOLDER = "info_bank"
    OUTPUT_FILE = "erasmus_hafiza.txt"
    extract_text_from_pdfs(INPUT_FOLDER, OUTPUT_FILE)
