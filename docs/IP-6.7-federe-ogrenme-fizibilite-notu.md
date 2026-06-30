# İP-6.7 — Federe Öğrenme (Faz-2) Fizibilite Notu

> **Durum:** Fizibilite değerlendirmesi (karar girdisi). Faz-2 yatırım kararı için
> teknik/hukuki çerçeve. İlgili: [[İP-4.2 mahremiyet-kapılı etiket]] (`app/learning/labels.py`),
> KVKK local-first mimari, [BIGG_AKSIYON_PLANI](BIGG_AKSIYON_PLANI.md).

## 1. Motivasyon
Her klinik on-prem çalışır ve hasta verisi kliniği terk etmez (KVKK çekirdek vaadi).
Ancak her kliniğin hekim onay/düzeltmeleri (İP-4.2) yönlendiriciyi iyileştiren değerli
bir sinyaldir. **Soru:** Bu sinyali, ham veriyi merkezileştirmeden, klinikler arası
**ortak bir modeli** iyileştirmek için kullanabilir miyiz? Federe öğrenme (FL) tam bu
problemi hedefler: model klinikte eğitilir, **yalnızca model güncellemeleri** paylaşılır.

## 2. Neden mimariyle uyumlu
- İP-4.2 zaten **ham hasta metnini taşımayan**, redaksiyon-kapılı etiket üretir →
  FL'nin "veri yerinde kalır" ilkesiyle birebir örtüşür.
- İP-2 yönetişim zarfı sınır-ötesi engeli ve denetim izini zaten sağlar → FL tur
  iletişimi aynı kapıdan denetlenebilir.
- Yönlendirici saf-Python ve küçük (kural+skor+kalibrasyon) → federe ortalanacak
  parametre uzayı küçük; ağır GPU/iletişim yükü yok.

## 3. Aday yaklaşımlar (artan koruma)
| Yaklaşım | Ne paylaşılır | Koruma | Maliyet/karmaşıklık |
|----------|----------------|--------|---------------------|
| **FedAvg** (temel) | Yerel model ağırlık/gradyan güncellemeleri | Ham veri paylaşılmaz | Düşük |
| **Secure Aggregation** | Maskeli güncellemeler (sunucu tekil katkıyı göremez) | + güncelleme gizliliği | Orta |
| **DP-FedAvg** (diferansiyel mahremiyet) | Gürültü-eklenmiş güncellemeler | + üyelik çıkarımına karşı kanıtlanabilir sınır | Orta-yüksek (doğruluk-mahremiyet dengesi) |

**Öneri:** Faz-2'de **Secure Aggregation + opsiyonel DP** hedefle; pilot doğrulaması
için sade **FedAvg** ile başla (az klinikle, kapalı çevrim).

## 4. KVKK / hukuki çerçeve
- Ham özel-nitelikli veri hiç hareket etmez → veri sorumlusu kliniktir; merkez yalnızca
  **anonim model güncellemesi** işler. Yine de güncellemelerin **dolaylı kişisel veri**
  taşımadığı (üyelik/gradyan sızıntısı) DP veya secure-agg ile güvence altına alınmalı.
- Federe tur, İP-2 zarfının **sınır-ötesi engel** ve **denetim izi** kapılarına tabi
  tutulmalı; güncelleme alışverişi yurt içi/sözleşmeli altyapıda kalmalı.
- Klinik sözleşmesine "federe model iyileştirmesine katılım" için **ayrı açık rıza**
  maddesi eklenmeli (varsayılan kapalı, opt-in).

## 5. Teknik riskler ve azaltım
| Risk | Azaltım |
|------|---------|
| Gradyan/üyelik sızıntısı | Secure aggregation + DP gürültüsü; güncelleme boyutunu sınırla |
| Klinikler-arası dağılım kayması (non-IID) | İstemci-ağırlıklı ortalama; klinik-yerel ince-ayar katmanı |
| Zehirleme (kötü/hatalı güncelleme) | Robust aggregation (median/trimmed-mean) + İP-4.2 mahremiyet+bütünlük kapıları |
| Az sayıda klinikle istatistiksel güç | Faz-2'yi yeterli klinik (≥5–10) sonrası başlat; öncesinde merkezi-yerel hibrit |
| Mahremiyet-doğruluk dengesi (DP) | Önce DP'siz secure-agg ile fayda ölç, DP bütçesini ampirik ayarla |

## 6. Önkoşullar (Faz-2 başlamadan)
- [ ] İP-5 pilot ile **≥5 klinik** canlı (yeterli federe istemci).
- [ ] İP-4.2 etiket akışı klinik başına üretimde ve redaksiyon-onayı süreci işler.
- [ ] Federe tur için yurt-içi/sözleşmeli toplayıcı altyapı + İP-2 zarf entegrasyonu.
- [ ] Klinik rıza/sözleşme şablonuna federe katılım maddesi.

## 7. Karar / öneri
**Faz-1 (şimdi):** Federe öğrenme **erken**; önkoşul klinik tabanı yok. Bunun yerine
İP-4.2/4.3 ile **klinik-yerel iyileştirme** sürdürülür (her klinik kendi onaylarıyla
kendi modelini kalibre eder) — federe değer önermesinin temelini kurar.

**Faz-2 (≥5 klinik sonrası):** Secure-Aggregation tabanlı FedAvg pilotu; başarı ölçütü:
federe model, klinik-yerel modele kıyasla yönlendirme doğruluğu/kalibrasyonunda
**regresyonsuz iyileşme** + sızıntı testlerinde 0 ihlal. DP, fayda ölçüldükten sonra
opt-in eklenir.

**Sonuç:** Federe öğrenme mimariyle **uyumlu ve savunulabilir bir hendek** (her klinik
düzeltmesi paylaşılan modeli iyileştirir) ancak **klinik tabanına bağlı**; bugün
açmak yerine İP-5 pilotuna bağlı bir Faz-2 olarak konumlandırılır.
