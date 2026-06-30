# IP-6.1 - Fiyatlandirma ve Faturalama Modeli

> Durum: Ticari model taslagi. Gercek fiyatlar pilot gorusmeleri ve odeme
> istekliligi sinyalleriyle valide edilmelidir.

## 1. Konumlandirma
CogniVault, dis klinikleri icin "AI receptionist" degil; KVKK-uyumlu, hekim
denetimli klinik on-buro isletim sistemi olarak fiyatlanir. Fiyat, mesaj sayisina
degil, kurtarilan randevu kapasitesine, operator zamanina ve risk azaltimina
baglanmalidir.

## 2. Paketler

| Plan | Aylik fiyat | Hedef musteri | Dahil |
|---|---:|---|---|
| Starter | 7.500 TL | Tek uniteli klinik | Public hasta sayfasi, KVKK onay, web chat, temel operator inbox |
| Growth | 18.500 TL + basarili randevu basi 75 TL | 2-5 uniteli klinik | WhatsApp/web, shadow review, kalibre triyaj, slot onerisi, haftalik rapor |
| Enterprise | Ozel fiyat | Cok subeli klinik/poliklinik | On-prem kurulum, gelismis audit, SLA, PMS/HBYS entegrasyonu, ozel raporlama |

## 3. Basari Bazli Ucret

**Basarili randevu:** CogniVault akisi uzerinden olusan ve klinik tarafindan
iptal edilmeyen randevu. No-show durumunda ucretlendirme pilotta klinik lehine
esnek tutulur; ucretli fazda "tamamlanan randevu" veya "onayli randevu" modeli
klinikle secilir.

**Onerilen cap:** Growth paketinde basari bazli ucret aylik sabit ucretin %100'unu
asmayacak sekilde ilk 3 ay tavanlanir. Bu, klinik icin risk algisini dusurur.

## 4. Birim Ekonomi Varsayimi

| Varsayim | Deger |
|---|---:|
| Tek klinik aylik sabit gelir | 7.500-18.500 TL |
| Basari ucreti | 75 TL / randevu |
| 100 basarili randevu ek geliri | 7.500 TL |
| Growth potansiyel aylik gelir | 26.000 TL |
| Yillik Growth degeri | 312.000 TL |

Bu model, mevcut proje dosyasindaki yaklasik ARPA seviyesine uyumludur; pilot
sonrasi gercek randevu hacmiyle yeniden kalibre edilmelidir.

## 5. Faturalama Olaylari

Backend tarafinda `billing_service.py` temeli oldugu icin ilk uygulanacak olaylar:

- `subscription_started`
- `subscription_renewed`
- `appointment_created_by_ai`
- `appointment_confirmed_by_clinic`
- `appointment_completed`
- `appointment_no_show`
- `plan_changed`
- `trial_converted`

## 6. Faturalama Kapilari

Ucret yazmadan once:
- KVKK/onay akisi tamamlanmis olmali.
- Randevu klinik tarafindan gorulebilir ve audit log'a yazilmis olmali.
- No-show veya iptal kurali plan sozlesmesine gore uygulanmali.
- Hekim/insan incelemesi gereken bir karar otomatik basari sayilmamali.

## 7. Pilot Donusum Teklifi

### Design Partner
- 30 gun pilot.
- Kurulum ucreti yok veya dusuk.
- Haftalik rapor ve urun geri bildirimi zorunlu.
- Referans izni alinabilirse ilk 3 ay %20 indirim.

### Ucretli Growth'a gecis
- Pilot metrikleri yesilse Growth plan onerilir.
- Ilk 3 ay basari ucreti tavanli.
- PMS entegrasyonu ayri proje veya Enterprise'a upgrade olarak fiyatlanir.

## 8. Satis Mesaji

Klinige soylenmesi gereken net teklif:
"CogniVault, mesai disi ve yogun saatlerde kacirdiginiz hasta taleplerini
KVKK-uyumlu sekilde toplar, acil/riskli durumlari insana yukseltir, randevuya
donusebilecek talepleri operatorunuzun onune hazir getirir. Biz bot satmiyoruz;
kaybolan kapasiteyi ve uyum riskini yoneten bir klinik on-buro katmani kuruyoruz."

## 9. Valide Edilecek Sorular

- Klinik sabit ucreti mi, basari ucretini mi daha adil buluyor?
- Randevu basari ucreti "olusan", "onaylanan" veya "tamamlanan" randevuda mi kesilmeli?
- PMS entegrasyonu icin ayri kurulum ucreti kabul ediliyor mu?
- Referans indirimi klinikleri motive ediyor mu?
- Starter plan cok ucuz kalip Growth'a gecisi yavaslatiyor mu?

## 10. Sonraki Teknik Adim

`billing_service.py` icin minimal MVP:
- Plan tanimi ve klinik plan atamasi.
- Faturalama olay kaydi.
- Aylik ozet raporu.
- Basari ucreti tavanlama.
- No-show/iptal kurali.

Gercek odeme entegrasyonu pilot sonrasi secilmelidir; erken asamada manuel fatura
ve aylik rapor yeterlidir.
