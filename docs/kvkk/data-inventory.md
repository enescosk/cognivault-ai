# Kişisel Veri Envanteri (VERBİS Hazırlık)

KVKK kapsamında işlenen tüm veri kategorileri, hukuki sebep, alıcı grubu ve saklama süreleri. Bu tablo VERBİS kaydı yapılırken doğrudan kullanılabilecek formatta.

> **Veri sorumlusu:** [CogniVault şirket adı — VERBİS'te resmi unvan]
> **Veri sorumlusu temsilcisi:** [Atanacak]
> **İrtibat kişisi (KVKK):** [Atanacak]

---

## 1. İlgili kişi grupları

| Grup | Açıklama |
|---|---|
| Hasta / Hizmet alan | Klinik aracılığıyla AI asistanla iletişime geçen gerçek kişi |
| Klinik personeli | Doktor, sekreter, klinik admin (sistem kullanıcısı) |
| Sistem kullanıcısı | CogniVault çalışanı, geliştirici |

---

## 2. Veri kategorileri

### A. Genel kişisel veriler

| Veri | Kaynak | Hukuki sebep (m.5) | Saklama |
|---|---|---|---|
| Ad-soyad | Hasta beyanı (kanal) | Sözleşmenin kurulması (m.5/2-c) — randevu sözleşmesi | Sözleşme sona erdikten 10 yıl (TBK m.146) veya hasta talebiyle silinene kadar |
| Telefon numarası | Hasta beyanı | Sözleşme + meşru menfaat (iletişim) | 10 yıl |
| Dil tercihi | Hasta beyanı / otomatik tespit | Meşru menfaat (m.5/2-f) | Konuşma kaydıyla aynı süre |
| Kanal kimliği (WA, telefon) | Otomatik | Sözleşme | Konuşma süresi + 90 gün |

### B. Özel nitelikli kişisel veriler (m.6) — sağlık verisi

| Veri | Kaynak | Hukuki sebep (m.6/3) | Saklama |
|---|---|---|---|
| Sağlık şikayeti metni | Hasta beyanı (yazılı/sözlü) | **Açık rıza** (zorunlu — kamu sağlığı istisnası uygulanmaz) | 90 gün (anonimleştirme), 1 yıl (silme) |
| Geçirilmiş ameliyat/hastalık beyanı | Hasta beyanı | **Açık rıza** | 90 gün anonim, 1 yıl sil |
| İlaç kullanım beyanı | Hasta beyanı | **Açık rıza** | 90 gün anonim, 1 yıl sil |
| Ses kaydı (raw audio) | Telefon kanalı | **Açık rıza** (biyometrik+sağlık) | 30 gün (transcript varsa) |
| Transcript | STT işleme | Açık rıza (kaynak sesle aynı) | 90 gün anonim |
| Triage sonucu (intent, risk) | AI çıktısı | Açık rıza (türev veri) | Konuşmayla aynı |
| Randevu kaydı | Sistem | Sözleşme + Sağlık Bakanlığı yönetmeliği | Sağlık Bakanlığı süresine tabi (genelde 20 yıl) |

> **NOT:** "Acil tıbbi durum" tespit edildiğinde KVKK m.6/3-b "tıbbi teşhis, sağlık hizmetleri yürütülmesi" istisnası **kısmen** uygulanabilir, ancak bu durumda da veri sır saklama yükümlülüğü altındaki kişilerce işlenmelidir. Otomatik AI işlemesi için bu istisna **tartışmalı** — avukat onayı gerekli.

### C. İşlem güvenliği verileri

| Veri | Hukuki sebep | Saklama |
|---|---|---|
| IP adresi | Meşru menfaat (güvenlik) | 2 yıl |
| Audit log (kim, ne, ne zaman) | Hukuki yükümlülük (m.12) | 2 yıl |
| Login/session bilgisi | Meşru menfaat | 1 yıl |

---

## 3. Veri alıcı grupları

| Alıcı | Veri kategorisi | Aktarım sebebi | Lokasyon |
|---|---|---|---|
| Klinik (veri sorumlusu sıfatıyla — ortak veya bağımsız) | A + B + Randevu | Hizmetin sunulması | TR |
| Klinik personeli (doktor, sekreter) | A + B (RBAC ile) | Hizmet sunumu | TR |
| Meta WhatsApp Cloud API | A + B (mesaj transit) | Kullanıcı kanal tercihi | ABD/AB ⚠️ |
| Twilio Voice | A + B (ses transit) | Telefon kanalı | ABD ⚠️ |
| **OpenAI (mevcut)** | A + B | AI işleme | **ABD ⚠️ — KALDIRILACAK** |
| Sağlık Bakanlığı (HBYS entegrasyonu varsa) | Randevu | Yasal yükümlülük | TR |
| Bulut altyapı sağlayıcı | Tümü | Hosting | **TR (hedef)** |

---

## 4. Yurt dışı aktarım analizi

KVKK m.9 hükmü gereği yurt dışı aktarım için:
- (a) İlgili kişinin **açık rızası**, **VEYA**
- (b) Yeterli korumanın bulunduğu ülke (Kurul kararı), **VEYA**
- (c) Veri sorumlularının yazılı taahhüdü + Kurul izni (BCR/SCC), **VEYA**
- Madde 5/2 ve 6/3'teki şartlardan biri + Yeterli koruma yoksa yazılı taahhüt + Kurul izni

**Mevcut durumda OpenAI'a aktarım için yukarıdaki şartlardan hiçbiri sağlanmıyor.** Kurul'un 2020-2024 kararlarında ABD "yeterli koruma bulunmayan ülke" konumunda. Bu kritik bir uyumsuzluk noktası.

**Hedef:** Faz 2 sonrası özel nitelikli sağlık verisi **hiç** yurt dışına çıkmayacak. Sadece Meta WhatsApp transit ve Twilio (alternatif bulunana kadar) kalacak; bunlar için de hasta'dan ayrı açık rıza alınacak (m.9/1-a).

---

## 5. Açık rıza beyanı — toplama yöntemi (önerilen)

KVKK Kurulu kararları "açık rızanın belirli, bilgilendirilmiş, özgür irade ile ispatlanabilir" olmasını arıyor. Bu sistemde:

1. **Telefon kanalı:**
   - Sabit IVR anonsu (versiyonlanmış)
   - "Kabul ediyorum" sözlü onay + DTMF tuşlama (çift onay)
   - Onay anının ses kaydı **ayrı**, şikayet kaydından önce saklanır
   - SMS ile aydınlatma metni link'i gönderilir (yazılı izi tamamlar)

2. **WhatsApp/Web:**
   - İlk mesajda buton/link ile aydınlatma + onay
   - Onay tıklamasına bağlı timestamp + IP + user-agent loglanır

3. **Reddetme:**
   - Otomatik canlı operatöre transfer
   - AI hiçbir veri işlemez, mesaj retention'dan kısa süre sonra silinir

---

## 6. Veri sahibi hakları (m.11) — endpoint planı

| Hak | Teknik karşılık | Endpoint (planlı) |
|---|---|---|
| Bilgi talep | "Hakkımda ne biliyorsunuz" | `GET /api/patient/data-export` |
| Düzeltme | Yanlış kayıt güncelleme | `PATCH /api/patient/me` |
| Silme | Tüm kişisel verinin silinmesi | `POST /api/patient/erasure-request` (insan onayı) |
| İşlemeyi durdurma | Açık rıza geri çekme | `POST /api/patient/consent/revoke` |
| Aktarıldığı kişiler | Audit log raporu | `GET /api/patient/disclosure-log` |

Şu anda bu endpoint'lerin hiçbiri yok. **Faz 4 (PII + audit) altında inşa edilecek.**
