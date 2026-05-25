# Avukat Görüşmesi Brief'i

> Bu doküman, KVKK avukatı/danışmanı ile yapılacak ilk görüşmede sunulacak özet ve avukata sorulacak somut soruları içerir. Görüşme öncesi avukata bu paketin tamamını paylaşmanız önerilir.

---

## 1 Sayfa Özet

**Ürün:** CogniVault Clinical — kliniklere (diş, estetik, fizyoterapi vb.) satılan, hastaların randevu ve şikayet taleplerini WhatsApp / telefon / web chat üzerinden **otomatik karşılayan** yapay zeka asistanı.

**Veri sorumlusu rolü:** CogniVault'un rolü tartışmalı — muhtemelen **bir kısımda veri işleyen (processor), bir kısımda ortak veri sorumlusu (joint controller)**. Bu görüşmenin ilk konusu.

**İşlenen veri:**
- Hasta adı-soyad, telefon (genel kişisel)
- **Sağlık şikayeti, geçirilmiş hastalık, ameliyat beyanı, ilaç bilgisi (özel nitelikli — KVKK m.6)**
- Ses kaydı (özel nitelikli + biyometrik)
- Randevu kaydı

**Mevcut teknik akış (KISA):**
1. Hasta kliniği arar / WhatsApp yazar
2. Sistem mesajı/sesi alır
3. AI (şu anda **OpenAI / ABD**) niyeti analiz eder ve cevap üretir
4. Cevap hastaya gönderilir veya doktor inbox'a düşer
5. Tüm konuşma PostgreSQL'de saklanır (şu anda **şifrelenmemiş, saklama süresi yok**)

**Bilinen risk:**
- Sağlık verisinin **OpenAI üzerinden ABD'ye aktarımı** (m.6 + m.9 ihlali olası)
- **Açık rıza akışı yok** — şu an her hasta veriyi otomatik veriyor
- **Retention/silme politikası yok**
- **VERBİS kaydı yapılmadı**
- **Aydınlatma metni yok**
- **Veri sahibi hakları (m.11) endpoint'leri yok**

**Planlanan çözüm:** Tüm AI işleme **Türkiye sınırlarında**, **lokal modellerle** (Qwen2.5-7B + faster-whisper + Coqui XTTS) yapılacak. Detay: [../ai-stack-decision.md](../ai-stack-decision.md)

---

## Avukata sorulacak 12 spesifik soru

### A — Rol ve sorumluluk

**1.** CogniVault'un KVKK karşısında rolü nedir?
   - Klinik **veri sorumlusu**, biz **veri işleyen** mi?
   - Yoksa **ortak veri sorumlusu** mu (joint controllership)?
   - Bu karar ileride sözleşmelerimizin (klinikle imzalanan SaaS sözleşmesi) iskeletini belirleyecek.

**2.** AI'ın otomatik karar vermesi (örn. "bu hastayı doktora aktar" / "randevuyu şu slota koy") **KVKK m.11/g "otomatik sistem ile analiz edilme"** kapsamına girer mi? Hastanın bu hakkını nasıl korumalıyız?

### B — Açık rıza akışı

**3.** Telefon kanalında sözlü açık rıza + DTMF tuş kombinasyonu Kurul kararları açısından geçerli sayılır mı? Yoksa **mutlaka yazılı ek onay** (SMS link + tıklama) mi gerekli?

**4.** "Aydınlatma metnini sesli okumak" zorunlu mu, yoksa **"detaylar SMS ile link olarak gönderilmiştir"** demek yeterli mi? Anonsun tam metnini nasıl yapılandırmalıyız?

**5.** Aydınlatma metni versiyonu değişirse **eski rıza geçersiz mi**? Tekrar onay almak zorunda mıyız (versioning stratejisi)?

**6.** Hasta açık rızayı reddederse hizmet vermeyi reddetmek **"açık rızanın özgür irade ile alınması"** ilkesini ihlal eder mi (m.5/1)? Alternatif yolu nasıl sunmalıyız?

### C — Yurt dışı aktarım

**7.** Meta WhatsApp Cloud API (mesaj transit) ve Twilio (ses transit) **kaçınılmaz transit aracıları** olarak m.9 kapsamında ayrı açık rıza gerektiriyor mu, yoksa hasta o kanalı seçerek **dolaylı rıza** sayılır mı?

**8.** Local AI stack'e geçtikten sonra **hiç yurt dışı aktarım kalmayacak şekilde** mimari kurmamız mı şart, yoksa "düşük riskli" türev veriler (örn. anonim model telemetrisi) için aktarım yapabilir miyiz?

**9.** Pilot dönemde (Faz 1-2 tamamlanmadan) **demo amaçlı OpenAI kullanımı** için ne yapmalıyız? Aydınlatma metninde açıkça yazıp pilot katılımcılardan ayrı imzalı onay almak yeterli mi?

### D — Saklama, silme, hakları

**10.** Sağlık verisi için **anonim saklama süreleri** (90 gün anonimleştirme, 1 yıl tam silme) yeterli mi? Sağlık Bakanlığı yönetmeliğiyle çelişki var mı (özellikle randevu/triage kayıtları)?

**11.** Hasta "verilerimi sil" derse, **doktor onayı olmadan sistematik silme** yapabilir miyiz? "Hekimlik kaydı tutma" yükümlülüğü ile KVKK silme hakkı çakışması nasıl çözülür?

### E — Sertifikasyon ve denetim

**12.** Bu sistemi kliniklere satabilmek için **ISO 27001 / ISO 27701 / TS 13298** gibi sertifikasyon zorunlu mu, yoksa "iyi mühendislik + iç denetim" yeterli mi? VERBİS kaydı en geç ne zaman yapılmalı?

---

## Görüşme sonrası beklenen çıktılar

Görüşmeden çıkacak somut belgeler:
1. **Hukuki yönlendirme notu** (avukat tarafından) — yukarıdaki 12 sorunun cevapları
2. **Aydınlatma metni taslağı** (avukat hazırlar, biz teknik koşulları söyleriz)
3. **Açık rıza beyanı taslağı** (kanal başına — telefon, WhatsApp, web)
4. **Klinikle imzalanacak Veri İşleyen Sözleşmesi taslağı** (DPA)
5. **VERBİS kaydı için danışmanlık fiyat teklifi**
6. **Pilot dönem için "feragatname / pilot programı katılım sözleşmesi"** (OpenAI'lı dönem için geçici çözüm)

Bu çıktılarla engineering Faz 1-7 başlatılır.

---

## Avukatın ihtiyaç duyabileceği ek bilgi

- [data-flow-map.md](data-flow-map.md) — teknik akış
- [data-inventory.md](data-inventory.md) — veri envanteri
- [risk-register.md](risk-register.md) — risk değerlendirmesi
- [../ai-stack-decision.md](../ai-stack-decision.md) — teknoloji seçimi
- [../CUSTOMER_INTAKE_ARCHITECTURE.md](../CUSTOMER_INTAKE_ARCHITECTURE.md) — kanal mimarisi
- Hedef müşteri profili (klinik tipi, hasta hacmi) — **buraya senin ekleyeceğin satır**
- Şirketin ticari kuruluş durumu (LTD/AŞ, VERBİS yükümlü mü) — **buraya senin ekleyeceğin satır**
