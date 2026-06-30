# IP-5.1 - Pilot Klinik Hatti Launch Pack

> Durum: Saha hazirlik paketi. Gercek pilot baslatmak icin klinik gorusmesi,
> sozlesme/riza imzalari ve canli kurulum gerekir.

## 1. Hedef
3-5 pilot klinigi 30 gunluk kontrollu saha denemesine almak; teknik kaliteyi,
KVKK guvenlik kapilarini, operasyonel faydayi ve ucretli donusum ihtimalini
olculebilir bicimde kanitlamak.

## 2. Pilot Klinik Secim Kriterleri

### Zorunlu kriterler
- Gunluk en az 25 hasta iletisimi veya haftalik 100+ inbound kanal kaydi.
- WhatsApp/telefon/web form kanallarindan en az ikisini aktif kullanma.
- Klinik sahibi veya yetkili yoneticinin haftalik 30 dk geri bildirim toplantisina
  katilmasi.
- KVKK aydinlatma/riza metnini pilot sureci icin guncellemeye acik olma.
- En az bir hekim veya klinik operatorunun shadow review ekranini kullanmasi.

### Ideal profil
- 1-5 uniteli ozel dis klinigi veya cok subeli kucuk poliklinik.
- Randevu kacirma, mesai disi mesaj, telefon yogunlugu veya no-show problemi net.
- PMS/HBYS entegrasyonu olmadan da ilk degeri gorebilecek operasyonel esneklik.

## 3. Pilot Teklifi

**Sure:** 30 gun kontrollu pilot + 15 gun ucretli donusum opsiyonu.  
**Kapsam:** WhatsApp/web hasta girisi, KVKK onay akisi, klinik triyaj, operator
inbox, shadow review, randevu taslagi, no-show/geri-cagirma raporu.  
**Pilot ucreti:** Design partner icin dusuk/sifir kurulum; basarili randevu ve
ucretli donusum kosullari onceden yazili.  
**Basari karari:** Asagidaki metriklerden en az 4'u yesilse ucretli plan gorusulur.

## 4. Basari Metrikleri

| Metrik | Hedef | Olcum |
|---|---:|---|
| Hasta memnuniyeti | >= %85 olumlu | Kisa anket + operator etiketi |
| Guvenlik kapisi ihlali | 0 | Governance audit log |
| Acil/escalation kacagi | 0 kritik kacis | Shadow review + olay kaydi |
| Ilk yanit suresi | p50 < 5 sn web, p50 < 30 sn WhatsApp | Kanal timestamp |
| Operator tasarrufu | >= %30 daha az manuel ilk cevap | Once/sonra islem sayisi |
| Randevu donusumu | >= %15 uplift veya net yeni randevu | Haftalik randevu raporu |
| No-show/geri-cagirma faydasi | >= %10 hatirlatma/geri-donus etkisi | Pilot cohort raporu |

## 5. Sozlesme ve KVKK Checklist

- [ ] Pilot sozlesmesi: sure, kapsam, veri isleme rolleri, sorumluluk sinirlari.
- [ ] KVKK aydinlatma metni: AI destekli on buro, iletisim, randevu, kayit amaci.
- [ ] Acik riza maddeleri: proaktif geri-cagirma, ses isleme, federe/faz-2 katilim
      varsayilan kapali.
- [ ] Veri isleme envanteri: kanal, veri tipi, saklama suresi, isleyici.
- [ ] Non-SaMD sinir dili: tani/tedavi onermez; yonlendirme ve operasyon destekler.
- [ ] Canli destek/escalation sorumlusu: klinik ve CogniVault tarafinda isimli kisi.
- [ ] Olay yonetimi: acil vaka, yanlis yonlendirme, veri talebi, silme/duzeltme istegi.

## 6. 30 Gunluk Pilot Takvimi

### Gun -7 / -3: Hazirlik
- Klinik bilgileri, hekimler, hizmetler, calisma saatleri, marka renkleri toplanir.
- KVKK metni ve public hasta sayfasi onaylanir.
- Operator hesaplari acilir; demo ve canli ortam ayrilir.

### Gun 0: Go-live
- 60 dakikalik canli egitim.
- Ilk 20 hasta mesaji shadow mode'da izlenir.
- Acil/escalation ve KVKK loglari gun sonunda kontrol edilir.

### Gun 1-7: Stabilizasyon
- Gunluk 15 dk operasyon check.
- Yanlis brans, dusuk guven, operator editleri etiketlenir.
- Pilot dashboard ilk versiyonu olusturulur.

### Gun 8-21: Olcum
- Haftalik rapor: randevu donusumu, operator tasarrufu, guvenlik olaylari.
- Klinik geri bildirimi urun backlog'una etiketlenir.
- No-show/geri-cagirma sinyalleri test edilir.

### Gun 22-30: Karar
- Basari metrikleri yesil/sari/kirmizi olarak raporlanir.
- Ucretli plan onerisi ve referans izni gorusulur.
- Pilot sonrasi veri saklama/silme karari alinip kayda girer.

## 7. Kabul Kapilari

Pilot "basarili" sayilmasi icin:
- Guvenlik kapisi ihlali 0.
- Klinik sahibi/yoneticisi yazili olumlu geri bildirim verir.
- En az 50 gercek hasta iletisi veya yeterli kanal hacmi islenir.
- En az 1 operator ve 1 hekim shadow review akisina dokunur.
- Ucretli plana gecis icin net sponsor ve tarih belirlenir.

## 8. Dis Bagimliliklar

Bu paket repoda tamamdir; ancak asagidaki maddeler masa basinda kapatilamaz:
- Kliniklerin bulunmasi ve gorusmelerin yapilmasi.
- Sozlesme/KVKK metinlerinin avukat tarafindan onaylanmasi.
- Canli hasta verisi ve operator/hekim geri bildirimi.
- PMS/HBYS entegrasyonu gerekiyorsa ilgili vendor erisimi.
