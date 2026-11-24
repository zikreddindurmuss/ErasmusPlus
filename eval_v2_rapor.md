# Erasmus++ — Değerlendirme v2 Raporu

> Bu rapor `python eval_v2.py report` ile `eval_v2_results.jsonl` dosyasından otomatik üretildi. En alttaki öneriler bölümü elle yazıldı.

## Özet

| Metrik | Değer |
|---|---|
| **Genel doğruluk** — (doğru cevap + doğru ret) / toplam | **%70.0** (35/50) |
| **Halüsinasyon oranı** — halüsinasyon / toplam | **%8.0** (4/50) |
| **Gereksiz ret oranı** — gereksiz ret / toplam | **%22.0** (11/50) |
| Cevaplı sorularda doğru cevap | %62.5 (25/40) |
| Cevaplı sorularda gereksiz ret | %27.5 (11/40) |
| Cevaplı sorularda halüsinasyon | %10.0 (4/40) |
| Cevapsız sorularda doğru ret | %100.0 (10/10) |
| Cevapsız sorularda halüsinasyon | %0.0 (0/10) |

### Sınıf dağılımı

| Sınıf | Cevaplı (n=40) | Cevapsız (n=10) | Toplam |
|---|---|---|---|
| DOĞRU CEVAP | 25 | 0 | 25 |
| DOĞRU RET | 0 | 10 | 10 |
| GEREKSİZ RET | 11 | 0 | 11 |
| HALÜSİNASYON | 4 | 0 | 4 |

Halüsinasyon alt tipleri: eksik_alakasiz: 2, yanlis: 2

## Kurulum ve tekrarlanabilirlik

| | |
|---|---|
| Cevap veren model (bot) | `openai/gpt-oss-120b` (Groq, temperature=0) |
| Hakem modeli | `qwen/qwen3.8-27b` (Groq, temperature=0, seed=42) — bottan farklı model ailesi (Alibaba Qwen vs OpenAI gpt-oss) |
| Soru üretim modeli | `qwen/qwen3.8-27b` |
| Embedding / retrieval | OpenAI `text-embedding-3-small`, FAISS, k=5 + konu boost (k=4) — `ai_engine.py` değiştirilmeden |
| Değerlendirme tarihi | 2026-11-22 02:04 → 2026-11-22 14:16 |
| Soru seti oluşturma | 2026-11-22 01:51:28 (seed=42) |
| Git commit | `d4cb6cf` + **commit edilmemiş `ai_engine.py` değişikliği** (model `GROQ_MODEL` env değişkeninden okunuyor, varsayılan gpt-oss-120b) |
| FAISS index (`index.faiss` md5) | `bd180f01814de4a9d5268f2921f11d29` |
| Soru sayısı | 50 (40 cevaplı + 10 cevapsız = %20) |

Yeniden çalıştırmak için: `eval_v2_results.jsonl` dosyasını silip `python eval_v2.py run` ve ardından `python eval_v2.py report`. Soru seti `eval_v2_questions.json` içinde donduruldu; yeniden üretilmez. LLM'ler temperature=0'da bile Groq'ta birebir deterministik değildir; tekrar koşularda birkaç soruluk sapma beklenebilir.

## Teşhis

- **Retrieval isabeti:** Cevaplı 40 sorunun 23 tanesinde (%57.5) sorunun üretildiği kaynak chunk, botun gördüğü bağlama girdi.
- Gereksiz retlerin 11/11 tanesinde kaynak chunk bağlamda **yoktu** (retrieval hatası); 0/11 tanesinde bağlamda olduğu hâlde model reddetti (prompt/okuma hatası).
- **Hakem ↔ anahtar kelime dedektörü uyumu:** `test_ai.py` tarzı fallback dedektörü ile hakemin ret/ret-değil kararı 47/50 soruda (%94.0) örtüşüyor.

## Başarısız örnekler (15)

### A04 — HALÜSİNASYON / eksik_alakasiz

- **Soru:** Erasmus Öğrenim Hareketliliği hangi belgeler ve anlaşmalar çerçevesinde gerçekleştirilir?
- **Beklenen cevap:** Standart veya Genişletilmiş Erasmus Üniversite Beyannamesi çerçevesinde ve yükseköğretim kurumunun Erasmus değişim anlaşmaları doğrultusunda.
- **Kaynak:** 2025 PROJE DÖNEMİ (2026-2027 Akademik Yılı) ERASMUS ÖĞRENİM HAREKETLİLİĞİ İLANI – AB Eğitim Programları Koordinatörlüğü.pdf — s.8
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, Erasmus Öğrenim Hareketliliği resmi olarak **Öğrenim Anlaşması (Learning Agreement / OLA)** çerçevesinde yürütülür. Bu anlaşma, senin yurt dışındaki kurumda alacağın derslerin programını ve bu derslerin kendi üniversitenizde tam akademik tanınmasını garanti eder. Anlaşma, **Erasmus Without Paper (EWP)** sistemi üzerinden elektronik olarak hazırlanıp imzalanır; “Create Learning Agreement” butonuyla oluşturulur, koordinatörün onayıyla “Office Approved” durumuna geçer ve EWP üzerinden karşı kuruma gönderilir.    Ayrıca, **davet mektubu** da sürecin bir parçasıdır. Yerleştirildiğin üniversite, başvuru sürecini tamamladıktan sonra sana bir davet mektubu gönderir; bu mektup, üniversitemizi […]
- **Hata nedeni (hakem):** Bot, sorunun cevabı olan 'Erasmus Üniversite Beyannamesi' ve 'değişim anlaşmaları' bilgisini vermemiş; bunun yerine belgelerdeki prosedürel detayları (OLA, EWP, davet mektubu) cevap olarak sunarak asıl soruyu yanıtlamamıştır.

### A11 — GEREKSİZ RET

- **Soru:** UJA'da İngilizce, Fransızca veya Almanca gibi başka dillerde verilen derslerin listesine hangi linkten ulaşabilirim?
- **Beklenen cevap:** https://uvirtual.ujaen.es/pub/es/informacionacademica/catalogofichasdocentesasignaturas/p/patie/2025-26
- **Kaynak:** Procedures in the UJA_incoming mobility.docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA’nın web portalından ya da uluslararası ilişkiler koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (spesifik URL) belgelerde mevcut olmasına rağmen, bot bilgiyi veremeyip 'rehberde yok' diyerek kullanıcıyı yönlendirmiştir.

### A12 — GEREKSİZ RET

- **Soru:** UJA'da Erasmus değişim programı bitiminde 'Certificate of Completion of Stay' belgesini almak için hangi ofise başvurmalıyım?
- **Beklenen cevap:** Uluslararası İlişkiler Ofisi'ne (International Relations Section, C2-105, 23071 Jaén) başvurmalısınız.
- **Kaynak:** Procedures in the UJA_incoming mobility.docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA’nın portalından ya da koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Cevap belgelerde mevcuttur (Uluslararası İlişkiler Ofisi) ancak bot bilgiyi veremeyip 'rehberde yok' diyerek ret etmiştir.

### A14 — GEREKSİZ RET

- **Soru:** UJA'da Erasmus öğrencisi olarak Learning Agreement'i kaç kez değiştirebilirim?
- **Beklenen cevap:** Sadece bir kez değiştirebilirsiniz.
- **Kaynak:** Procedures in the UJA_incoming mobility.docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın kaç kez değiştirilebileceğiyle ilgili net bir sayı elimdeki resmi rehberde yok. UJA’nın Erasmus portalındaki “During the Mobility” (Add/Drop) sürecini ya da koordinatöründen teyit etmeni öneririm.
- **Hata nedeni (hakem):** Beklenen cevap (bir kez değiştirilebileceği) belgelerde mevcut olmasına rağmen, bot bilgiyi veremeyip 'rehberde yok' diyerek ret etmiştir.

### A24 — GEREKSİZ RET

- **Soru:** UJA Erasmus platformunda ders eşleştirmelerini yaparken neden önce UJA derslerini doldurup sonra hedef üniversite derslerini eklememeliyim?
- **Beklenen cevap:** Bu durumda platform kilitlenecektir.
- **Kaynak:** InstruccionesParaLaTramitacionErasmus2022-23.pdf — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA’nın portalından ya da koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Cevap belgelerde mevcuttur (platformun kilitleneceği bilgisi) ancak bot bu bilgiyi veremeyip 'rehberde yok' diyerek reddetmiştir.

### A25 — HALÜSİNASYON / eksik_alakasiz

- **Soru:** UJA'daki Erasmus sözleşmemde ders değişikliği yaparsam, eski dersin kaydını iptal etmem ve yeni derse kayıt olmam için ne yapmam gerekiyor?
- **Beklenen cevap:** Sözleşmeden çıkardığınız orijinal dersin kaydını iptal etmeli ve yeni derse kayıt olmalısınız; bunun için UJA'da ders değişikliği için bir kayıt dönemi açılır.
- **Kaynak:** InstruccionesParaLaTramitacionErasmus2022-23.pdf — s.3
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, ders değişikliği yapmak için şu adımları izlemelisin:  1. **EWP OLA (Online Learning Agreement) platformuna gir**      - https://erasmusport.ankara.edu.tr adresine kullanıcı adı‑şifrenle giriş yap.      - “Başvurularım > Öğrenim Başvurularım > Öğrenim Anlaşması” sekmesine tıkla (Kaynak 6, 7, 8).  2. **Dersleri ADD/DROP ile değiştir**      - Seçmek istediğin yeni dersi **ADD** işaretiyle, artık almayacağın eski dersi **DROP** işaretiyle işaretle.      - Değişikliği kaydet ve “Tamamla” butonuna bas (Kaynak 2, 7).  3. **Onay sürecini başlat**      - Kaydettiğin değişiklik aynı onay silsilesiyle ilerler: önce sen imzalar, ardından Ankara Üniversitesi koordinatörün ve son olarak Universid […]
- **Hata nedeni (hakem):** Bot, sorunun özünü oluşturan 'UJA'da ders değişikliği için özel bir kayıt dönemi açılır' bilgisini vermemiş; bunun yerine Ankara Üniversitesi'nin genel ADD/DROP prosedürünü ve EWP onay süreçlerini detaylandırarak asıl soruyu yanıtlamamıştır.

### A26 — HALÜSİNASYON / yanlis

- **Soru:** UJA'da bir acil durum (kaza, hırsızlık vb.) yaşandığında aranması gereken genel acil durum numarası nedir?
- **Beklenen cevap:** 112
- **Kaynak:** PROTOCOL EMERGENCIES_STUDENTS MOBILITY.docx.pdf — s.5
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, UJA’da acil bir durum (kaza, hırsızlık vb.) yaşadığında aranması gereken genel acil durum numarası **(+34) 913 799 700**’dür. Bu numara, üniversitenin 24‑saat hizmet veren acil durum hattıdır.
- **Hata nedeni (hakem):** Beklenen cevap genel acil durum numarası olan 112 iken, bot belge parçasındaki üniversiteye özel 24 saatlik yardım hattı numarasını (+34) 913 799 700'ü genel acil durum numarası olarak yanlışlıkla vermiştir.

### A27 — GEREKSİZ RET

- **Soru:** UJA'da Erasmus öğrencisi olarak acil sağlık hizmetlerine başvururken kimlik belgesi olarak ne sunmam gerekiyor?
- **Beklenen cevap:** Pasaport veya kimlik kartı
- **Kaynak:** PROTOCOL EMERGENCIES_STUDENTS MOBILITY.docx.pdf — s.3
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (pasaport veya kimlik kartı) belgelerde mevcut olmasına rağmen, bot bilgiyi veremeyip 'rehberde yok' diyerek ret etmiştir.

### A28 — GEREKSİZ RET

- **Soru:** UJA'ya Erasmus olarak giden öğrencilerin sunması gereken sağlık sigortası poliçesi hangi İspanyol sigorta şirketlerinden alınabilir?
- **Beklenen cevap:** ASISA, UNIVERSITAS, MUNDI, AXA, ONCAMPUS, GENERALI SEGUROS, ADESLAS, SANITAS, CIGNA, DKV, MAFRE SEGUROS
- **Kaynak:** national_SSU_SLU_Student.pdf — s.2
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA’nın “referans olarak gösterdiği” sigorta şirketlerinden sadece **OnCampus** örnek olarak geçiyor. Başka bir İspanyol sigorta şirketi adı kaynaklarda yer almıyor; bu yüzden başka bir firma ismi veremiyorum. Poliçeyi nereden alabileceğinle ilgili kesin bilgi için UJA Uluslararası İlişkiler ve İşbirliği Servisi’nin portalına ya da koordinatörüne danışman iyi olur.
- **Hata nedeni (hakem):** Beklenen cevapta listelenen sigorta şirketleri (ASISA, UNIVERSITAS vb.) kaynak belgelerde açıkça yer almasına rağmen, bot bu bilgileri veremeyip sadece 'OnCampus' örneğini göstererek kullanıcıyı yönlendirmiştir.

### A29 — GEREKSİZ RET

- **Soru:** UJA'ya Erasmus için gelen öğrencilerde vize reddi durumunda itiraz hakkı ne kadar süre içinde kullanılabilir?
- **Beklenen cevap:** Vize reddi bildirimini aldıkları tarihten itibaren 1 ay içinde yazılı olarak itiraz edebilirler.
- **Kaynak:** national_SSU_SLU_Student.pdf — s.4
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Cevap belgelerde mevcut olmasına rağmen (1 ay içinde itiraz hakkı), bot bilgiyi veremeyip 'rehberde yok' diyerek ret etmiştir.

### A33 — GEREKSİZ RET

- **Soru:** Erasmus+ programı kapsamında UJA'da İspanyolca derslerine kayıt olmak için bir yarıyıl içinde en fazla kaç ders alabilirim ve bu derslerin toplam ECTS değeri nedir?
- **Beklenen cevap:** En fazla 2 ders (1 genel + 1 spesifik) alınabilir ve toplam ECTS değeri 12'dir.
- **Kaynak:** _Información cursos de español CEALM 25-26 (Info para coordinadores, estudiantes y buddies).docx — s.1
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA’da bir yarıyıl içinde alabileceğin İspanyolca (ELE) ders sayısı ve bu derslerin toplam ECTS değeriyle ilgili net bir sınır yok. CEALM’in sunduğu her İspanyolca dersi 60 saat ve **6 ECTS** değerinde, ama bir yarıyıla kaç tane ders ekleyebileceğin konusunda belge içinde bir rakam ya da kural bulunmuyor.  Bu yüzden kesin rakamı öğrenmek için **UJA Uluslararası İlişkiler ve İşbirliği Servisi**’ne ya da **CEALM koordinatörlerine** danışmanı, ayrıca Erasmus portalındaki “Learning Agreement” (Öğrenim Anlaşması) kısmını kontrol etmeni öneririm. Oradan ders kontenjanları ve ECTS limitleri netleşir. Başarılar!
- **Hata nedeni (hakem):** Belgelerde (Kaynak 5) bir yarıyıl için en fazla 2 ders ve 12 ECTS sınırı açıkça belirtilmesine rağmen, bot bu bilgiyi bulamadığını iddia edip kullanıcıyı yönlendirmiştir.

### A34 — GEREKSİZ RET

- **Soru:** 2026-2027 Akademik Yılı Erasmus+ programına yerleşen öğrencilerin faaliyetlerini en geç hangi tarihte tamamlaması gerekiyor?
- **Beklenen cevap:** 31.07.2027
- **Kaynak:** 2025 Proje Dönemi (2026-2027 Akademik Yılı) Erasmus Öğrenim Hareketliliği Nihai Sonuçları – AB Eğitim Programları Koordinatörlüğü.pdf — s.2
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde 2026‑2027 akademik yılına dair faaliyetlerin en geç ne zaman bitirilmesi gerektiğiyle ilgili bir tarih bulunmuyor. Bu detayı UJA’nın portalından ya da koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (31.07.2027) belgelerde mevcut olmasına rağmen, bot cevabı bulamadığını iddia ederek kullanıcıyı yönlendirmiştir.

### A36 — HALÜSİNASYON / yanlis

- **Soru:** Vize/başlangıç gecikmeleri yüzünden henüz Türkiye'deyken İspanya'daki evinin kirasını boşuna ödemek zorunda kalan Erasmus öğrencisi aylık ne kadar kira ödüyordu?
- **Beklenen cevap:** Aylık 339 Euro gibi bir tutar (Nisan ve Mayıs kiralarını Türkiye'den ödemek zorunda kaldı).
- **Kaynak:** Erasmus Grupları ve Öğrenci Sorunları Araştırması.pdf — s.5
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde bu durumla ilgili net bir rakam 400 ‑ 500 Euro arasında aylık kira ödemesi olduğu belirtilmiş. Yani vize gecikmesi yüzünden Türkiye’deyken boşuna ödediği kira, ayda yaklaşık **400‑500 Euro** tutmuş.
- **Hata nedeni (hakem):** Beklenen cevap aylık 339 Euro iken bot, belgelerde genel piyasa aralığı olarak geçen 400-500 Euro rakamını spesifik olayın cevabı olarak vererek belgeyle çelişen yanlış bir bilgi sunmuştur.

### A39 — GEREKSİZ RET

- **Soru:** UJA'da 2025-2026 akademik yılı için Noel tatili ne zaman başlıyor ve bitiyor?
- **Beklenen cevap:** 22 Aralık 2025'ten 6 Ocak 2026'ya kadar.
- **Kaynak:** CG202324_anexo10_Calendario_académico_2025_2026_Aprobado.pdf — s.2
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, bu adımın detayları elimdeki resmi rehberde yok, UJA'nın portalından veya koordinatöründen teyit etmen lazım.
- **Hata nedeni (hakem):** Beklenen cevap (22 Aralık 2025 - 6 Ocak 2026) kaynak belgelerde mevcut olmasına rağmen, bot bilgiyi veremeyip kullanıcıyı yönlendirmiştir.

### A40 — GEREKSİZ RET

- **Soru:** UJA 2025-2026 akademik takviminde CE2 kısaltması neyi ifade ediyor?
- **Beklenen cevap:** Convocatoria Extraordinaria II (İkinci Olağanüstü Sınav Dönemi)
- **Kaynak:** CG202324_anexo10_Calendario_académico_2025_2026_Aprobado.pdf — s.4
- **Kaynak chunk bağlamda mıydı:** hayır
- **Bot cevabı:** Dostum, elimdeki resmi rehberde UJA 2025‑2026 akademik takvimindeki **CE2** kısaltmasının ne anlama geldiğiyle ilgili bir bilgi yok. Bu detayı UJA’nın öğrenci portalından ya da uluslararası ilişkiler koordinatöründen teyit etmen gerekiyor.
- **Hata nedeni (hakem):** Cevap belgelerde mevcut olmasına rağmen bot, bilgiyi veremeyip kullanıcıyı yönlendirmiştir.

## Tüm sonuçlar

| ID | Tür | Sınıf | Kaynak bağlamda | Soru |
|---|---|---|---|---|
| A01 | cevapli | DOĞRU CEVAP | ✓ | Erasmus başvurusu sırasında 14.12.2025 tarihli Merkezi Erasmus Dil Sınavına giren öğrencilerin sisteme hangi belgeyi yüklemesi gerekiyor? |
| A02 | cevapli | DOĞRU CEVAP | ✓ | Erasmus hareketliliğinde yeşil seyahat desteği alabilmek için seyahatin ne kadarının yeşil araçlarla yapılması gerekiyor? |
| A03 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrenim hareketliliğinde aynı öğrenim kademesinde (lisans, yüksek lisans veya doktora) bir öğrenci toplamda en fazla kaç ay hibe ala […] |
| A04 | cevapli | HALÜSİNASYON | ✗ | Erasmus Öğrenim Hareketliliği hangi belgeler ve anlaşmalar çerçevesinde gerçekleştirilir? |
| A05 | cevapli | DOĞRU CEVAP | ✓ | Erasmus programında diş hekimliği fakültesi 2. sınıf öğrencileri kaç dönem için yerleştirilir? |
| A06 | cevapli | DOĞRU CEVAP | ✓ | Jaén'e uçakla gelmek için en yakın havalimanı hangisidir ve şehre uzaklığı kaç kilometredir? |
| A07 | cevapli | DOĞRU CEVAP | ✓ | Jaén eyaletinde İspanya genelindeki en büyük korunan doğal alanlara sahip olduğu doğru mu? |
| A08 | cevapli | DOĞRU CEVAP | ✓ | UJA'nın (Pre-academic) yoğun İspanyolca dil ve kültür kursu hangi öğrenci gruplarına yöneliktir? |
| A09 | cevapli | DOĞRU CEVAP | ✓ | UJA'da öğrencilerin kullanımına açık toplam kaç bilgisayar laboratuvarı bulunmaktadır? |
| A10 | cevapli | DOĞRU CEVAP | ✓ | UJA'da resmi master programlarına başvuru işlemleri hangi birim tarafından yürütülüyor? |
| A11 | cevapli | GEREKSİZ RET | ✗ | UJA'da İngilizce, Fransızca veya Almanca gibi başka dillerde verilen derslerin listesine hangi linkten ulaşabilirim? |
| A12 | cevapli | GEREKSİZ RET | ✗ | UJA'da Erasmus değişim programı bitiminde 'Certificate of Completion of Stay' belgesini almak için hangi ofise başvurmalıyım? |
| A13 | cevapli | DOĞRU CEVAP | ✗ | UJA'da Erasmus öğrencisi olarak vize başvurusu için gerekli olan kabul mektubu ve diğer belgeler nereden temin edilir? |
| A14 | cevapli | GEREKSİZ RET | ✗ | UJA'da Erasmus öğrencisi olarak Learning Agreement'i kaç kez değiştirebilirim? |
| A15 | cevapli | DOĞRU CEVAP | ✓ | UJA'da ev kiralarken 'desgaste normal' (normal kullanım aşınması) kapsamındaki hasarlar için ev sahibi depozitodan kesinti yapabilir mi? |
| A16 | cevapli | DOĞRU CEVAP | ✓ | UJA'da Erasmus öğrencisi olarak ev kiralarken ödemem gereken depozito (fianza) yasal olarak en fazla kaç aylık kira tutarını kapsayabilir? |
| A17 | cevapli | DOĞRU CEVAP | ✓ | UJA'ya sunulacak özel sigorta poliçesinde veya onay mektubunda açıkça belirtilmesi zorunlu olan 5 ana teminat maddesi bulunmazsa evrak ne ol […] |
| A18 | cevapli | DOĞRU CEVAP | ✓ | Erasmus Öğrenim Anlaşması (Learning Agreement) formu hangi adresten doldurulmalıdır? |
| A19 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrenim anlaşmamın durumu 'Pending Applicant Delivery' olarak görünüyorsa ne yapmam gerekiyor? |
| A20 | cevapli | DOĞRU CEVAP | ✗ | Ankara Üniversitesi'nde Erasmus öğrenim hareketliliği için hazırlanan belgeler nereden yüklenmeli ve bu işlem yapılmazsa ne olur? |
| A21 | cevapli | DOĞRU CEVAP | ✓ | Erasmus+ öğrenim anlaşması (Learning Agreement) belgesi karşı kurum tarafından e-posta ile gönderilirse Ankara Üniversitesi sisteminde nasıl […] |
| A22 | cevapli | DOĞRU CEVAP | ✓ | Erasmus Öğrenim Anlaşması (Learning Agreement) formunu doldurmaya başlamak için hangi adresi kullanmam gerekiyor? |
| A23 | cevapli | DOĞRU CEVAP | ✓ | 2024 proje dönemi kapsamında 2025-2026 Erasmus+ öğrenim hareketliliği en geç hangi tarihte sona ermelidir? |
| A24 | cevapli | GEREKSİZ RET | ✗ | UJA Erasmus platformunda ders eşleştirmelerini yaparken neden önce UJA derslerini doldurup sonra hedef üniversite derslerini eklememeliyim? |
| A25 | cevapli | HALÜSİNASYON | ✗ | UJA'daki Erasmus sözleşmemde ders değişikliği yaparsam, eski dersin kaydını iptal etmem ve yeni derse kayıt olmam için ne yapmam gerekiyor? |
| A26 | cevapli | HALÜSİNASYON | ✗ | UJA'da bir acil durum (kaza, hırsızlık vb.) yaşandığında aranması gereken genel acil durum numarası nedir? |
| A27 | cevapli | GEREKSİZ RET | ✗ | UJA'da Erasmus öğrencisi olarak acil sağlık hizmetlerine başvururken kimlik belgesi olarak ne sunmam gerekiyor? |
| A28 | cevapli | GEREKSİZ RET | ✗ | UJA'ya Erasmus olarak giden öğrencilerin sunması gereken sağlık sigortası poliçesi hangi İspanyol sigorta şirketlerinden alınabilir? |
| A29 | cevapli | GEREKSİZ RET | ✗ | UJA'ya Erasmus için gelen öğrencilerde vize reddi durumunda itiraz hakkı ne kadar süre içinde kullanılabilir? |
| A30 | cevapli | DOĞRU CEVAP | ✓ | Erasmus kapsamında 500 ila 1999 km mesafe için standart seyahat hibesi ne kadardır? |
| A31 | cevapli | DOĞRU CEVAP | ✓ | Erasmus seçim kriterlerinde engelli öğrencilere kaç puan eklenir? |
| A32 | cevapli | DOĞRU CEVAP | ✓ | UJA'da Self-enrollment sırasında 'No appointment available' hatası alırsam ne yapmam gerekiyor? |
| A33 | cevapli | GEREKSİZ RET | ✗ | Erasmus+ programı kapsamında UJA'da İspanyolca derslerine kayıt olmak için bir yarıyıl içinde en fazla kaç ders alabilirim ve bu derslerin t […] |
| A34 | cevapli | GEREKSİZ RET | ✗ | 2026-2027 Akademik Yılı Erasmus+ programına yerleşen öğrencilerin faaliyetlerini en geç hangi tarihte tamamlaması gerekiyor? |
| A35 | cevapli | DOĞRU CEVAP | ✓ | Erasmus öğrencileri için ev bulma sürecinde 'Erasmus Life', 'Spacest' veya 'Uniplaces' gibi ajansların sunduğu hizmetlerin en büyük dezavant […] |
| A36 | cevapli | HALÜSİNASYON | ✗ | Vize/başlangıç gecikmeleri yüzünden henüz Türkiye'deyken İspanya'daki evinin kirasını boşuna ödemek zorunda kalan Erasmus öğrencisi aylık ne […] |
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
| A39 | cevapli | GEREKSİZ RET | ✗ | UJA'da 2025-2026 akademik yılı için Noel tatili ne zaman başlıyor ve bitiyor? |
| A40 | cevapli | GEREKSİZ RET | ✗ | UJA 2025-2026 akademik takviminde CE2 kısaltması neyi ifade ediyor? |

<!-- MANUEL BÖLÜM: bu satırın altı rapor yeniden üretilirken korunur -->

## Koşu notları ve elle denetim (elle yazıldı)

**Koşu:** 50 sorunun tamamı tamamlandı. İlk koşu 39. soruda Groq günlük token limitine (gpt-oss-120b, 200k TPD) takıldı. Kalan 11 soru limit açılınca (2026-11-22 14:06) aynı soru setiyle, kod ve index değişmeden kaldığı yerden çalıştırıldı. Limit yüzünden "HATA" olarak kaydedilen soru yok.

**Hakem etiketlerinin elle denetimi:** 50 etiketin hepsini okudum. Başarısız 15 örneğin 13'üne katılıyorum. Sınırda olan 2 örnek:
- **A04:** Soru çok genel; botun OLA/EWP cevabı tamamen yanlış değil.
- **A26:** Bot 112 yerine belgedeki UJA 24 saat hattını "genel acil numara" diye verdi.

Bu ikisi DOĞRU CEVAP sayılsaydı genel doğruluk %74 olurdu. Raporda hakemin etiketi esas alındı. Doğru sayılan 35 örnekte yanlış pozitif görmedim. A38'de bot `${user}` yer tutucusunu aynen aktarıyor; doğru ama kullanıcıya faydasız.

**Ana teşhis:**
- **Kaynak bota ulaşmıyor:** Gereksiz retlerin 11/11'inde ve halüsinasyonların 4/4'ünde, sorunun üretildiği chunk birebir eşleşmeyle botun bağlamında yoktu. Tek istisna A33: aynı CEALM sayfasından başka bir chunk bağlamdaydı ve hakem cevabın orada olduğunu söylüyor. Yani A33 bir okuma/prompt hatası.
- **Tek belge bağlamı dolduruyor:** `Erasmus+ Öğrenci Bilgi Veri Seti Oluşturma.pdf` index'in %27'si (174/641 chunk). 50 sorunun 31'inde, başarısız 15 örneğin 14'ünde bağlamda yer alıyor ve top-5'in çoğunu (özellikle s.8/9) dolduruyor.
- **Sonuç:** Sorun büyük ölçüde model okumasında değil, retrieval'da.
- **Cevapsız sorular:** 10/10 doğru ret, hiç uydurma yok. Halüsinasyon önleme kuralı (KURAL 3) güçlü çalışıyor, ama aynı kural bilgi bağlama gelmediğinde gereksiz rete dönüşüyor.

## Gereksiz retleri azaltmak için öneriler (uygulanmadı)

1. **Baskın belgeyi frenle: kaynak başına çeşitlilik + MMR.** `similarity_search(k=5)` yerine `max_marginal_relevance_search(k=8, fetch_k=30)` kullan ve aynı dosyadan en fazla 2 chunk al. Başarısız 15 örneğin 14'ünde aynı "Veri Seti" belgesi (çoğunlukla s.8/9) bağlamda ve sıklıkla 3-4 slotu kaplıyor. Beklenen etki en yüksek ve maliyeti düşük.
2. **k'yi artır + reranker ekle.** İlk aşamada k=20-30 aday getir, bir cross-encoder (ör. `bge-reranker-v2-m3`, çok dilli) ile 6-8'e indir. Sorular Türkçe, kaynakların yarısı İngilizce/İspanyolca (A11, A12, A14, A24, A27, A29; takvim belgesi A39/A40 İspanyolca). Saf embedding benzerliği diller arası eşleşmede zayıf. Alternatif: sorguyu İngilizce/İspanyolca'ya çevirip ek arama (çok dilli sorgu genişletme).
3. **Prompt: kısmi bilgi varsa ver, reddi son çare yap + ikinci şans retrieval.** KURAL 3 şu an "cevap yoksa SADECE fallback cümlesini söyle" diyor. Bu, model bağlamdaki bilgiyi gözden kaçırdığında (A33: CEALM chunk bağlamdaydı ama "sınır yok" dedi) doğrudan rete dönüşüyor. Öneriler: (a) "Önce tüm kaynakları tara; ilgili kısmi bilgi varsa onu ver, sonra eksik kısmı belirt" kuralı, (b) bot fallback verdiğinde daha geniş k ve BOOST'suz ikinci bir arama ile tekrar deneme.

Ek gözlemler: Korpusta iki yol haritası sürümü çelişkili portal adresi veriyor (A18/A20/A21/A22). Eski sürüm temizlenmeli. Chunk boyutu (1000/150) bu ölçümde birincil sorun olarak görünmüyor.
