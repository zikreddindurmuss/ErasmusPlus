# Erasmus++ — Değerlendirme v2 Raporu

> Bu rapor `python eval_v2.py report` ile `eval_v2_results.jsonl` dosyasından otomatik üretildi. En alttaki öneriler bölümü elle yazıldı.

## Özet

| Metrik | Değer |
|---|---|
| **Genel doğruluk** — (doğru cevap + doğru ret) / toplam | **%80.0** (40/50) |
| **Halüsinasyon oranı** — halüsinasyon / toplam | **%6.0** (3/50) |
| **Gereksiz ret oranı** — gereksiz ret / toplam | **%14.0** (7/50) |
| Cevaplı sorularda doğru cevap | %75.0 (30/40) |
| Cevaplı sorularda gereksiz ret | %17.5 (7/40) |
| Cevaplı sorularda halüsinasyon | %7.5 (3/40) |
| Cevapsız sorularda doğru ret | %100.0 (10/10) |
| Cevapsız sorularda halüsinasyon | %0.0 (0/10) |

### Sınıf dağılımı

| Sınıf | Cevaplı (n=40) | Cevapsız (n=10) | Toplam |
|---|---|---|---|
| DOĞRU CEVAP | 30 | 0 | 30 |
| DOĞRU RET | 0 | 10 | 10 |
| GEREKSİZ RET | 7 | 0 | 7 |
| HALÜSİNASYON | 3 | 0 | 3 |

Halüsinasyon alt tipleri: eksik_alakasiz: 2, yanlis: 1

## Kurulum ve tekrarlanabilirlik

| | |
|---|---|
| Cevap veren model (bot) | `openai/gpt-oss-120b` (Groq, temperature=0) |
| Hakem modeli | `qwen/qwen3.8-27b` (Groq, temperature=0, seed=42) — bottan farklı model ailesi (Alibaba Qwen vs OpenAI gpt-oss) |
| Soru üretim modeli | `qwen/qwen3.8-27b` |
| Embedding / retrieval | OpenAI `text-embedding-3-small`, FAISS, k=5 + konu boost (k=4), mod: `mmr_cap` |
| Koşu adı | `adim1` |
| Değerlendirme tarihi | 2026-11-22 15:18 → 2026-11-22 21:30 |
| Soru seti oluşturma | 2026-11-22 01:51:28 (seed=42) |
| Git commit | `d4cb6cf` + **commit edilmemiş `ai_engine.py` değişikliği** (model `GROQ_MODEL` env değişkeninden okunuyor, varsayılan gpt-oss-120b) |
| FAISS index (`index.faiss` md5) | `bd180f01814de4a9d5268f2921f11d29` |
| Soru sayısı | 50 (40 cevaplı + 10 cevapsız = %20) |

Yeniden çalıştırmak için: `eval_v2_results.jsonl` dosyasını silip `python eval_v2.py run` ve ardından `python eval_v2.py report`. Soru seti `eval_v2_questions.json` içinde donduruldu; yeniden üretilmez. LLM'ler temperature=0'da bile Groq'ta birebir deterministik değildir; tekrar koşularda birkaç soruluk sapma beklenebilir.

## Teşhis

- **Retrieval isabeti:** Cevaplı 40 sorunun 26 tanesinde (%65.0) sorunun üretildiği kaynak chunk, botun gördüğü bağlama girdi.
- Gereksiz retlerin 7/7 tanesinde kaynak chunk bağlamda **yoktu** (retrieval hatası); 0/7 tanesinde bağlamda olduğu hâlde model reddetti (prompt/okuma hatası).
- **Hakem ↔ anahtar kelime dedektörü uyumu:** `test_ai.py` tarzı fallback dedektörü ile hakemin ret/ret-değil kararı 49/50 soruda (%98.0) örtüşüyor.

## Başarısız örnekler (10)

### A04 — HALÜSİNASYON / eksik_alakasiz

- **Soru:** Erasmus Öğrenim Hareketliliği hangi belgeler ve anlaşmalar çerçevesinde gerçekleştirilir?
- **Beklenen cevap:** Standart veya Genişletilmiş Erasmus Üniversite Beyannamesi çerçevesinde ve yükseköğretim kurumunun Erasmus değişim anlaşmaları doğrultusunda.
- **Kaynak:** 2025 PROJE DÖNEMİ (2026-2027 Akademik Yılı) ERASMUS ÖĞRENİM HAREKETLİLİĞİ İLANI – AB Eğitim Programları Koordinatörlüğü.pdf — s.8
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, Erasmus + Öğrenim Hareketliliği esas olarak **Learning Agreement (Öğrenim Anlaşması)** çerçevesinde yürütülür.  - **Online Learning Agreement (OLA/EWP)**: “Başvurularım > Öğrenim Başvurularım > Öğrenim Anlaşması” sekmesinden derslerini seçip kaydedersin, “Create Learning Agreement” butonunu aktif hâle getirirsin. Anlaşma senin ve ev sahibi kurumun onayına girer, “Office Approved” durumuna geldiğinde EWP (Erasmus Without Paper) sistemi üzerinden karşı kuruma gönderilmiş olur. Bu süreçte imza durumunu ekranın sağ üst köşesindeki “Durum” kısmından takip edebilirsin.    - **Paper Learning Agreement**: EWP sistemi hâlâ tam uyum sağlamamışsa, web sitesindeki “Belgeler ve Formlar” sekmesind […]
- **Hata nedeni (hakem):** Bot, sorunun cevabı olan 'Erasmus Üniversite Beyannamesi' ve 'değişim anlaşmaları' bilgisini vermemiş; bunun yerine belgelerde yer alan ancak soruyla doğrudan ilgili olmayan 'Öğrenim Anlaşması (Learning Agreement)' prosedürlerini cevap olarak sunmuştur.

### A07 — GEREKSİZ RET

- **Soru:** Jaén eyaletinde İspanya genelindeki en büyük korunan doğal alanlara sahip olduğu doğru mu?
- **Beklenen cevap:** Evet, Jaén, İspanya genelindeki en büyük korunan doğal alanlara sahiptir.
- **Kaynak:** UJAINTERNATIONALGUIDE.pdf — s.4
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu konuda elimdeki resmi rehberde bilgi yok; Jaén’in İspanya genelindeki korunan doğal alanların büyüklüğüyle ilgili detayları UJA’nın portalından ya da koordinatöründen teyit etmen gerekiyor.
- **Hata nedeni (hakem):** Cevap belgelerde mevcut olmasına rağmen (Kanıt: 'Jaén possesses the largest extension of protected natural areas...'), bot bilgiyi veremeyip 'rehberde yok' diyerek reddetti.

### A10 — GEREKSİZ RET

- **Soru:** UJA'da resmi master programlarına başvuru işlemleri hangi birim tarafından yürütülüyor?
- **Beklenen cevap:** Servicio de Gestión Académica (Campus Las Lagunillas s/n, Secretaría Única, Edif. B5)
- **Kaynak:** UJAINTERNATIONALGUIDE.pdf — s.26
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (Servicio de Gestión Académica) belgelerde mevcut olmasına rağmen bot, bilgiyi veremeyip kullanıcıyı yönlendirmiştir.

### A11 — GEREKSİZ RET

- **Soru:** UJA'da İngilizce, Fransızca veya Almanca gibi başka dillerde verilen derslerin listesine hangi linkten ulaşabilirim?
- **Beklenen cevap:** https://uvirtual.ujaen.es/pub/es/informacionacademica/catalogofichasdocentesasignaturas/p/patie/2025-26
- **Kaynak:** Procedures in the UJA_incoming mobility.docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA’nın İngilizce, Fransızca ya da Almanca gibi dillerde sunduğu derslerin listesinin bulunduğu belirli bir link yer almıyor. Bu konuda en güncel ve doğru bilgiyi UJA’nın uluslararası koordinatöründen ya da üniversitenin resmi Erasmus portalından (örneğin https://erasmusport.ankara.edu.tr) teyit etmen gerekiyor.
- **Hata nedeni (hakem):** Beklenen cevap (link) belgelerde mevcut olmasına rağmen, bot bu bilgiyi veremeyip 'rehberde yok' diyerek kullanıcıyı yönlendirmiştir.

### A12 — GEREKSİZ RET

- **Soru:** UJA'da Erasmus değişim programı bitiminde 'Certificate of Completion of Stay' belgesini almak için hangi ofise başvurmalıyım?
- **Beklenen cevap:** Uluslararası İlişkiler Ofisi'ne (International Relations Section, C2-105, 23071 Jaén) başvurmalısınız.
- **Kaynak:** Procedures in the UJA_incoming mobility.docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA’nın portalından ya da uluslararası ilişkiler ofisi/akademik koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (Uluslararası İlişkiler Ofisi) kaynak belgelerde açıkça mevcuttur ancak bot, bilgiyi veremeyip kullanıcıyı yönlendirmiştir.

### A26 — HALÜSİNASYON / yanlis

- **Soru:** UJA'da bir acil durum (kaza, hırsızlık vb.) yaşandığında aranması gereken genel acil durum numarası nedir?
- **Beklenen cevap:** 112
- **Kaynak:** PROTOCOL EMERGENCIES_STUDENTS MOBILITY.docx.pdf — s.5
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, UJA’da bir acil durum (kaza, hırsızlık vb.) yaşandığında aranması gereken genel acil durum numarası **061**’dir.   Bu numara, sağlıkla ilgili acil durumları da kapsayan ulusal acil yardım hattıdır; gerektiğinde en yakın hastane ya da acil servis yönlendirilir.
- **Hata nedeni (hakem):** Beklenen cevap 112 iken bot, belgelerdeki yerel sağlık acil hattı olan 061 numarasını genel acil durum numarası olarak vererek yanlış bilgi sunmuştur.

### A27 — GEREKSİZ RET

- **Soru:** UJA'da Erasmus öğrencisi olarak acil sağlık hizmetlerine başvururken kimlik belgesi olarak ne sunmam gerekiyor?
- **Beklenen cevap:** Pasaport veya kimlik kartı
- **Kaynak:** PROTOCOL EMERGENCIES_STUDENTS MOBILITY.docx.pdf — s.3
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA’da acil sağlık hizmetlerine başvurduğunda hangi kimlik belgesini göstermen gerektiğiyle ilgili bir bilgi yok. Bu konuyu UJA’nın uluslararası ilişkiler ofisi ya da Erasmus koordinatöründen teyit etmen en doğrusu.
- **Hata nedeni (hakem):** Beklenen cevap (pasaport veya kimlik kartı) kaynak belgelerde mevcut olmasına rağmen, bot bu bilgiyi veremeyip 'rehberde yok' diyerek reddetmiştir.

### A28 — HALÜSİNASYON / eksik_alakasiz

- **Soru:** UJA'ya Erasmus olarak giden öğrencilerin sunması gereken sağlık sigortası poliçesi hangi İspanyol sigorta şirketlerinden alınabilir?
- **Beklenen cevap:** ASISA, UNIVERSITAS, MUNDI, AXA, ONCAMPUS, GENERALI SEGUROS, ADESLAS, SANITAS, CIGNA, DKV, MAFRE SEGUROS
- **Kaynak:** national_SSU_SLU_Student.pdf — s.2
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, UJA’ya Erasmusla giden öğrenciler, sağlık sigortası poliçesini Jaén’deki herhangi bir İspanyol sigorta şirketinden alabilirler. Kaynaklarda özellikle şu iki şirket örnek olarak verilmiş:  - **Mapfre** (www.mapfre.es) – Jaén’de doğrudan temin edilebilen bir İspanyol sigorta şirketi.   - **OnCampus** – UJA’nın referans gösterdiği şirketlerden biri; burada da poliçeler alınabiliyor.  Bu iki şirket, resmi rehberde belirtilen örneklerdir; başka bir İspanyol sigorta şirketi de tercih edilebilir, ancak kesin şirket isimleri olarak sadece **Mapfre** ve **OnCampus** kaynakta yer alıyor. (Kaynak 2, Kaynak 4)
- **Hata nedeni (hakem):** Bot, belgelerde yer alan 11 sigorta şirketinin listesini (ASISA, UNIVERSITAS, MUNDI vb.) verememiş ve sadece kaynaklarda geçen Mapfre ve OnCampus'u örnek olarak sunarak asıl soruyu (hangi şirketlerden alınabilir) eksik ve yanıltıcı bir şekilde cevaplamıştır.

### A29 — GEREKSİZ RET

- **Soru:** UJA'ya Erasmus için gelen öğrencilerde vize reddi durumunda itiraz hakkı ne kadar süre içinde kullanılabilir?
- **Beklenen cevap:** Vize reddi bildirimini aldıkları tarihten itibaren 1 ay içinde yazılı olarak itiraz edebilirler.
- **Kaynak:** national_SSU_SLU_Student.pdf — s.4
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA'ya Erasmus için gelen öğrencilerin vize reddi durumunda itiraz hakkının ne kadar süre içinde kullanılabileceğiyle ilgili bir bilgi yok. Bu konuyu UJA’nın Erasmus ofisi ya da vize koordinatöründen teyit etmen gerekiyor.
- **Hata nedeni (hakem):** Beklenen cevap (1 ay içinde itiraz) belgelerde mevcut olmasına rağmen, bot bilgiyi veremeyip 'rehberde yok' diyerek ret etmiştir.

### A33 — GEREKSİZ RET

- **Soru:** Erasmus+ programı kapsamında UJA'da İspanyolca derslerine kayıt olmak için bir yarıyıl içinde en fazla kaç ders alabilirim ve bu derslerin toplam ECTS değeri nedir?
- **Beklenen cevap:** En fazla 2 ders (1 genel + 1 spesifik) alınabilir ve toplam ECTS değeri 12'dir.
- **Kaynak:** _Información cursos de español CEALM 25-26 (Info para coordinadores, estudiantes y buddies).docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde bir yarıyıl içinde UJA’da alabileceğin maksimum İspanyolca dersi sayısı ve bu derslerin toplam ECTS değeriyle ilgili net bir bilgi yok. En güncel ve kesin detayları UJA’nın uluslararası ofisinden, Erasmus koordinatöründen ya da UJA portalındaki ders kataloğundan teyit etmen gerekiyor. Bol şans!
- **Hata nedeni (hakem):** Kaynak 2'de derslerin 6 ECTS olduğu ve genel/spesifik olmak üzere iki tür olduğu belirtilerek toplam 12 ECTS ve 2 ders limiti çıkarılabilmektedir; ancak bot bu bilgiyi veremeyip 'net bir bilgi yok' diyerek reddetmiştir.

## Tüm sonuçlar

| ID | Tür | Sınıf | Kaynak bağlamda | Soru |
|---|---|---|---|---|
| A01 | cevapli | DOĞRU CEVAP | ✓ | Erasmus başvurusu sırasında 14.12.2025 tarihli Merkezi Erasmus Dil Sınavına giren öğrencilerin sisteme hangi belgeyi yüklemesi gerekiyor? |
| A02 | cevapli | DOĞRU CEVAP | ✓ | Erasmus hareketliliğinde yeşil seyahat desteği alabilmek için seyahatin ne kadarının yeşil araçlarla yapılması gerekiyor? |
| A03 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrenim hareketliliğinde aynı öğrenim kademesinde (lisans, yüksek lisans veya doktora) bir öğrenci toplamda en fazla kaç ay hibe ala […] |
| A04 | cevapli | HALÜSİNASYON | ✗ | Erasmus Öğrenim Hareketliliği hangi belgeler ve anlaşmalar çerçevesinde gerçekleştirilir? |
| A05 | cevapli | DOĞRU CEVAP | ✓ | Erasmus programında diş hekimliği fakültesi 2. sınıf öğrencileri kaç dönem için yerleştirilir? |
| A06 | cevapli | DOĞRU CEVAP | ✓ | Jaén'e uçakla gelmek için en yakın havalimanı hangisidir ve şehre uzaklığı kaç kilometredir? |
| A07 | cevapli | GEREKSİZ RET | ✗ | Jaén eyaletinde İspanya genelindeki en büyük korunan doğal alanlara sahip olduğu doğru mu? |
| A08 | cevapli | DOĞRU CEVAP | ✓ | UJA'nın (Pre-academic) yoğun İspanyolca dil ve kültür kursu hangi öğrenci gruplarına yöneliktir? |
| A09 | cevapli | DOĞRU CEVAP | ✓ | UJA'da öğrencilerin kullanımına açık toplam kaç bilgisayar laboratuvarı bulunmaktadır? |
| A10 | cevapli | GEREKSİZ RET | ✗ | UJA'da resmi master programlarına başvuru işlemleri hangi birim tarafından yürütülüyor? |
| A11 | cevapli | GEREKSİZ RET | ✗ | UJA'da İngilizce, Fransızca veya Almanca gibi başka dillerde verilen derslerin listesine hangi linkten ulaşabilirim? |
| A12 | cevapli | GEREKSİZ RET | ✗ | UJA'da Erasmus değişim programı bitiminde 'Certificate of Completion of Stay' belgesini almak için hangi ofise başvurmalıyım? |
| A13 | cevapli | DOĞRU CEVAP | ✗ | UJA'da Erasmus öğrencisi olarak vize başvurusu için gerekli olan kabul mektubu ve diğer belgeler nereden temin edilir? |
| A14 | cevapli | DOĞRU CEVAP | ✓ | UJA'da Erasmus öğrencisi olarak Learning Agreement'i kaç kez değiştirebilirim? |
| A15 | cevapli | DOĞRU CEVAP | ✓ | UJA'da ev kiralarken 'desgaste normal' (normal kullanım aşınması) kapsamındaki hasarlar için ev sahibi depozitodan kesinti yapabilir mi? |
| A16 | cevapli | DOĞRU CEVAP | ✗ | UJA'da Erasmus öğrencisi olarak ev kiralarken ödemem gereken depozito (fianza) yasal olarak en fazla kaç aylık kira tutarını kapsayabilir? |
| A17 | cevapli | DOĞRU CEVAP | ✓ | UJA'ya sunulacak özel sigorta poliçesinde veya onay mektubunda açıkça belirtilmesi zorunlu olan 5 ana teminat maddesi bulunmazsa evrak ne ol […] |
| A18 | cevapli | DOĞRU CEVAP | ✗ | Erasmus Öğrenim Anlaşması (Learning Agreement) formu hangi adresten doldurulmalıdır? |
| A19 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrenim anlaşmamın durumu 'Pending Applicant Delivery' olarak görünüyorsa ne yapmam gerekiyor? |
| A20 | cevapli | DOĞRU CEVAP | ✗ | Ankara Üniversitesi'nde Erasmus öğrenim hareketliliği için hazırlanan belgeler nereden yüklenmeli ve bu işlem yapılmazsa ne olur? |
| A21 | cevapli | DOĞRU CEVAP | ✓ | Erasmus+ öğrenim anlaşması (Learning Agreement) belgesi karşı kurum tarafından e-posta ile gönderilirse Ankara Üniversitesi sisteminde nasıl […] |
| A22 | cevapli | DOĞRU CEVAP | ✓ | Erasmus Öğrenim Anlaşması (Learning Agreement) formunu doldurmaya başlamak için hangi adresi kullanmam gerekiyor? |
| A23 | cevapli | DOĞRU CEVAP | ✓ | 2024 proje dönemi kapsamında 2025-2026 Erasmus+ öğrenim hareketliliği en geç hangi tarihte sona ermelidir? |
| A24 | cevapli | DOĞRU CEVAP | ✓ | UJA Erasmus platformunda ders eşleştirmelerini yaparken neden önce UJA derslerini doldurup sonra hedef üniversite derslerini eklememeliyim? |
| A25 | cevapli | DOĞRU CEVAP | ✓ | UJA'daki Erasmus sözleşmemde ders değişikliği yaparsam, eski dersin kaydını iptal etmem ve yeni derse kayıt olmam için ne yapmam gerekiyor? |
| A26 | cevapli | HALÜSİNASYON | ✗ | UJA'da bir acil durum (kaza, hırsızlık vb.) yaşandığında aranması gereken genel acil durum numarası nedir? |
| A27 | cevapli | GEREKSİZ RET | ✗ | UJA'da Erasmus öğrencisi olarak acil sağlık hizmetlerine başvururken kimlik belgesi olarak ne sunmam gerekiyor? |
| A28 | cevapli | HALÜSİNASYON | ✗ | UJA'ya Erasmus olarak giden öğrencilerin sunması gereken sağlık sigortası poliçesi hangi İspanyol sigorta şirketlerinden alınabilir? |
| A29 | cevapli | GEREKSİZ RET | ✗ | UJA'ya Erasmus için gelen öğrencilerde vize reddi durumunda itiraz hakkı ne kadar süre içinde kullanılabilir? |
| A30 | cevapli | DOĞRU CEVAP | ✓ | Erasmus kapsamında 500 ila 1999 km mesafe için standart seyahat hibesi ne kadardır? |
| A31 | cevapli | DOĞRU CEVAP | ✓ | Erasmus seçim kriterlerinde engelli öğrencilere kaç puan eklenir? |
| A32 | cevapli | DOĞRU CEVAP | ✓ | UJA'da Self-enrollment sırasında 'No appointment available' hatası alırsam ne yapmam gerekiyor? |
| A33 | cevapli | GEREKSİZ RET | ✗ | Erasmus+ programı kapsamında UJA'da İspanyolca derslerine kayıt olmak için bir yarıyıl içinde en fazla kaç ders alabilirim ve bu derslerin t […] |
| A34 | cevapli | DOĞRU CEVAP | ✓ | 2026-2027 Akademik Yılı Erasmus+ programına yerleşen öğrencilerin faaliyetlerini en geç hangi tarihte tamamlaması gerekiyor? |
| A35 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrencileri için ev bulma sürecinde 'Erasmus Life', 'Spacest' veya 'Uniplaces' gibi ajansların sunduğu hizmetlerin en büyük dezavant […] |
| A36 | cevapli | DOĞRU CEVAP | ✓ | Vize/başlangıç gecikmeleri yüzünden henüz Türkiye'deyken İspanya'daki evinin kirasını boşuna ödemek zorunda kalan Erasmus öğrencisi aylık ne […] |
| A37 | cevapli | DOĞRU CEVAP | ✓ | Jaén'de üniversiteye giden veya üniversite çevresinde duran şehir içi toplu taşıma hatlarından biri olan Línea 4'ün güzergahı nedir? |
| A38 | cevapli | DOĞRU CEVAP | ✓ | UJA öğrenci e-postası (@red.ujaen.es) hangi e-posta altyapısını kullanıyor ve hangi kimlik bilgileriyle giriş yapılıyor? |
| U01 | cevapsiz | DOĞRU RET | — | UJA kampüsündeki yemekhanede (comedor) günün menüsü kaç euro? |
| U02 | cevapsiz | DOĞRU RET | — | Erasmus sırasında İspanya'da öğrenci olarak haftada en fazla kaç saat yarı zamanlı çalışabilirim? |
| U03 | cevapsiz | DOĞRU RET | — | Türk ehliyetimle İspanya'da kaç ay boyunca araba kullanabilirim? |
| U04 | cevapsiz | DOĞRU RET | — | Erasmus'a gitmeden önce askerlik tecilim için askerlik şubesine hangi belgeyi vermem gerekiyor? |
| U05 | cevapsiz | DOĞRU RET | — | Jaén'de belediyenin bisiklet kiralama sistemi var mı, aylık ücreti ne kadar? |
| U06 | cevapsiz | DOĞRU RET | — | UJA kampüsünde öğrenciler için otopark ücreti ne kadar? |
| U07 | cevapsiz | DOĞRU RET | — | UJA'nın kapalı yüzme havuzunu Erasmus öğrencileri kaç euroya kullanabiliyor? |
| U08 | cevapsiz | DOĞRU RET | — | UJA öğrenci kartıyla Jaén şehir otobüslerinde yüzde kaç indirim alıyorum? |
| U09 | cevapsiz | DOĞRU RET | — | Jaén'den Madrid'e trenle gitmek kaç euro tutuyor? |
| U10 | cevapsiz | DOĞRU RET | — | UJA'da Erasmus öğrencileri için yaz okulu (curso de verano) var mı, ücreti ne kadar? |
| A39 | cevapli | DOĞRU CEVAP | ✓ | UJA'da 2025-2026 akademik yılı için Noel tatili ne zaman başlıyor ve bitiyor? |
| A40 | cevapli | DOĞRU CEVAP | ✓ | UJA 2025-2026 akademik takviminde CE2 kısaltması neyi ifade ediyor? |

<!-- MANUEL BÖLÜM: bu satırın altı rapor yeniden üretilirken korunur -->

## Sonuç — Adım 0 + 1 (elle yazıldı)

**Değişiklik:** `ai_engine.py` içinde retrieval `retrieve_context()` fonksiyonuna taşındı (adım 0). `_retrieve` artık MMR (fetch_k=30, λ=0.7) kullanıyor ve her kaynak dosyadan en fazla 2 chunk alıyor (adım 1). Eski davranış `RETRIEVAL_MODE=similarity` ile geri açılabilir. Prompt, model, k=5 ve index değişmedi.

**Durum:** **50 sorunun 50'si** ölçüldü (Groq günlük limiti yüzünden 4 parça halinde, kaldığı yerden devam ederek; hiçbir soru hata kaydıyla geçilmedi).

**Baseline ile eşleştirilmiş karşılaştırma (aynı 50 soru):**

| | Baseline | Adım 1 |
|---|---|---|
| Doğru cevap | 25 | 30 |
| Doğru ret (cevapsız 10 soru) | 10 | 10 |
| Gereksiz ret | 11 | 7 |
| Halüsinasyon | 4 | 3 |
| **Doğruluk** | **%70.0** | **%80.0** |
| Halüsinasyon oranı | %8.0 | %6.0 |
| Gereksiz ret oranı | %22.0 | %14.0 |

- **Kazanılan (7):** A14, A24, A34, A39, A40 (gereksiz ret → doğru); A25, A36 (halüsinasyon → doğru). Yedisinde da kaynak chunk yeni modda bağlama giriyor, eskide girmiyordu (offline testle tutarlı).
- **Kaybedilen (3):** A07, A10 (doğru → gereksiz ret). Cevap UJA rehberinde ve rehber ilk 5'i haklı olarak dolduruyordu; kaynak başına 2 sınırı doğru chunk'ı kesti. A28 (gereksiz ret → halüsinasyon): kaynak iki koşuda da bağlamda yok, bot bu sefer liste yerine 2 şirket adı verdi (davranış oynaması, retrieval değişikliğine bağlanamaz).
- **Offline retrieval testi (Groq'suz, 40 cevaplı soru):** kaynak isabeti 23/40 → 26/40.

**Kabul ölçütleri:** gereksiz ret azaldı (11 → 7) ✓, halüsinasyon artmadı (4 → 3) ✓, cevapsız sorularda doğru ret %100 kaldı ✓. `test_ai.py` regresyonu: **14/14 test geçti** (24.11.2026, 429 hatası yok; 7 test doğru bilgiyle, 7 test güvenli fallback ile). 22.11.2026'daki ilk deneme Groq günlük limitine (429 TPD) takıldığı için geçersiz sayıldı.

**Yorum ve dürüstlük notları:**
- Net kazanç +5 doğru (7 kazanç, 2 doğruluk kaybı; A28 başarısız sınıflar arasında yer değiştirdi). 50 soruluk küçük bir sette bu yönsel olarak anlamlı ama istatistiksel olarak kesin değil; tek soru = 2 puan. Eşleştirilmiş sayımla 7'ye 2 (işaret testi, tek yönlü p ≈ 0.09).
- Kaynak başına sınır bir değiş-tokuş: dağınık bilgide kazandırıyor, cevabın tek büyük belgede yoğunlaştığı sorularda (A07, A10) kaybettiriyor. Sınırı 3'e çıkarmak bu kayıpları geri getirebilir ama bunu aynı test setinde ayarlamak aşırı uyum olur; ayrı bir doğrulama setiyle denenmeli.
- Parametreler (MAX_PER_SOURCE=2, fetch_k=30, λ=0.7) bu 50 soruya bakılarak ayarlanmadı.
