# IP-6.3 - <1 Gun Klinik Onboarding Playbook

> Durum: Operasyon playbook'u hazir. Gercek <1 gun hedefi, pilot klinikte
> kronometreli kurulumla dogrulanmalidir.

## 1. Onboarding Tanimi
Bir klinigin CogniVault Clinical'i ilk hasta temasina hazir hale getirmesi:
marka kimligi, hekim/hizmet bilgileri, calisma saatleri, KVKK metni, operator
hesaplari, public hasta sayfasi, shadow review ve temel randevu akisi.

**Hedef sure:** 6 saat aktif calisma + ayni gun canli smoke test.

## 2. Rollere Gore Sorumluluk

| Rol | Sorumluluk | Cikti |
|---|---|---|
| Klinik sahibi | Yetki, KVKK onayi, fiyat/plana karar | Imzali pilot/onboarding onayi |
| Klinik operatoru | Kanal ve randevu akisi bilgisi | Mesaj senaryolari, calisma saatleri |
| Hekim temsilcisi | Brans, acil/escalation kurallari | Hekim review kurallari |
| CogniVault teknik | Kurulum, seed, QA | Calisan ortam + rapor |
| CogniVault urun | Egitim, kabul testi | Onboarding kabul formu |

## 3. Klinik Bilgi Toplama Formu

### Klinik kimligi
- Klinik adi, slug, adres, telefon, web sitesi.
- Logo URL/dosyasi, ana renk, vurgu rengi.
- Hasta sayfasi basligi ve alt metni.

### Hekim ve hizmet
- Hekim adi, uzmanlik, aktif/pasif durumu.
- Hizmet listesi: ad, aciklama, ilgili hekim, ortalama sure.
- Acil/escalation kurallari: kanama, sislik, travma, implant komplikasyonu vb.

### Calisma ve slot
- Gunluk calisma saatleri.
- Hekim bazli slot suresi.
- Tatil/kapali gunler.
- No-show riskine gore tercih edilmeyen prime slotlar.

### KVKK ve iletisim
- Aydinlatma metni versiyonu.
- Proaktif geri-cagirma izni.
- Ses kaydi/STT izni.
- Veri saklama suresi ve silme talebi sorumlusu.

## 4. 6 Saatlik Kurulum Akisi

### Saat 0-1: Yetki ve bilgi alma
- Klinik intake formu doldurulur.
- Admin/operator kullanicilari acilir.
- KVKK metni ve public slug onaylanir.

### Saat 1-2: Klinik kimligi
- Branding ayarlari girilir.
- Public hasta sayfasi acilir.
- Mobil/desktop gorunum smoke test edilir.

### Saat 2-3: Hekim, hizmet, persona
- Hekimler ve hizmetler eklenir.
- Default persona ve escalation dili ayarlanir.
- Operator inbox ve shadow review rolleri kontrol edilir.

### Saat 3-4: Slot ve randevu akisi
- Slot kurallari girilir.
- Randevu taslagi ve onay akisi test edilir.
- No-show/geri-cagirma kapilari varsayilan kapali veya pilot modda acilir.

### Saat 4-5: KVKK ve guvenlik
- Aydinlatma metni, onay akisi ve audit log kontrol edilir.
- Acil, sigorta, kimlik ve dusuk-guven senaryolari insana yukseliyor mu test edilir.
- Sinir-otesi isleyici ayarlari local-first modda dogrulanir.

### Saat 5-6: Egitim ve kabul
- Operator/hasta/klinik admin akisi canli anlatilir.
- 10 senaryoluk kabul testi kosulur.
- Kabul formu imzalanir ve pilot gun 0 planlanir.

## 5. 10 Senaryoluk Kabul Testi

| # | Senaryo | Beklenen sonuc |
|---:|---|---|
| 1 | Hasta KVKK onayi verip sohbet baslatir | Session token + welcome message |
| 2 | Randevu ister | Uygun slot onerisi |
| 3 | Acil kanama bildirir | Otomatik insan/escalation |
| 4 | TC/kimlik yazar | Kimlik inceleme kapisi |
| 5 | Sigorta/provizyon sorar | Insan onayi/escalation |
| 6 | Belirsiz sikayet yazar | Cekimserlik veya dusuk-guven review |
| 7 | Operator conversation detail acar | Mesaj, risk, metadata gorunur |
| 8 | Hekim shadow review yapar | Onay/duzeltme/ret kaydi |
| 9 | Public sayfa marka rengini gosterir | Branding dogru |
| 10 | KVKK metni versiyonlu gorunur | Disclosure version kayitli |

## 6. Demo Veri Reset ve Ortam Disiplini

- Demo/veri tabani reset komutu pilot oncesi yalnizca demo ortamda kullanilir.
- Canli pilotta reset yok; silme/duzeltme talepleri audit log ile islenir.
- Seed demo kullanicilari prod ortamda kapali tutulur.
- Pilot klinik icin staging ve live slug ayrimi korunur.

## 7. <1 Gun Kabul Kriteri

Onboarding basarili sayilmasi icin:
- Baslangictan kabul formuna kadar aktif sure <= 6 saat.
- 10 kabul senaryosunun 10'u gecer veya kritik olmayan sapmalar backlog'a yazilir.
- Klinik operatoru yardimsiz conversation detail ve shadow review acabilir.
- Public hasta sayfasi klinik markasiyla calisir.
- KVKK/onay/audit izi dogrulanir.

## 8. Bloke Olan Maddeler

Asagidaki maddeler icin saha veya dis erisim gerekir:
- Gercek PMS/HBYS entegrasyonu.
- Klinik avukatinin KVKK metnini onaylamasi.
- Gercek telefon/WhatsApp Business hesabi baglama izinleri.
- Model damitim veya gercek-zamanli ses runtime optimizasyonu.
