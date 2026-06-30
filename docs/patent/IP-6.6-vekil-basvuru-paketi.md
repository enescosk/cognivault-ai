# IP-6.6 - Patent Vekili Basvuru Paketi

> **Durum:** Vekile teslim edilebilir teknik paket. Hukuki tavsiye degildir.
> Resmi novelty, bulus basamagi, istem kapsami ve basvuru dili patent vekili
> tarafindan kesinlestirilmelidir.
>
> Ilgili dosyalar: [IP-6.4-6.5 novelty ve istem taslaklari](IP-6.4-6.5-novelty-ve-istem-taslaklari.md),
> [IP-6.7 federe ogrenme fizibilite notu](../IP-6.7-federe-ogrenme-fizibilite-notu.md),
> [dental-ai-patent-dossier.md](../dental-ai-patent-dossier.md).

## 1. Vekile Tek Cumlelik Ozet
CogniVault AI, Turkce dental/klinik hasta iletisiminde olasiliksal dil ve ses
modellerini, local-first veri yerlesimi, deterministik yonetisim zarfi,
kalibre-cekimser triyaj ve hekim-onayli mahremiyet-kapili ogrenme dongusu ile
sinirlayarak otomatik yanit, randevu ve geri-cagirma kararlarini denetlenebilir
hale getiren bir klinik iletisim sistemidir.

## 2. Basvuru Kapsami Onerisi

### Ana bulus ailesi
**Bulus basligi taslagi:** Klinik iletisim sistemlerinde olasiliksal model
ciktilarinin deterministik yonetisim zarfi ve kalibre cekimser triyaj ile
denetlenmesi.

**Bagimsiz istem omurgasi:**
1. Deterministik klinik-yonetisim zarfi: veri sinifi tespiti, tani/tedavi
   engeli, acil/sigorta/kimlik/dusuk-guven insan-yukseltme, sinir-otesi isleyici
   engeli, PII maskeleme ve maskeli audit izi.
2. Kalibre + cekimser Turkce dental triyaj: normalizasyon, brans skorlama,
   ECE-kalibrasyonu, konformal/risk-kontrollu kabul esigi, acil-recall kapisi.
3. Hekim-onay paketi ve mahremiyet-kapili ogrenme: shadow-mode kararlarindan
   ham hasta metni tasimayan, redaksiyon-onayli egitim etiketi uretimi.

### Devam basvurusu / faz-2 adayi
Federe ogrenme, bugun ana basvuruya bagimli veya opsiyonel varyant olarak
anlatilabilir; ayri bir basvuru ailesi icin ise IP-5 sonrasi en az 5 klinik
pilot verisi beklenmelidir. Gerekce: teknik mimari uyumlu, fakat sahadaki
federe istemci tabani henuz yok.

## 3. Kanit ve Artefakt Matrisi

| Iddia | Repo kaniti | Mevcut sonuc | Vekile not |
|---|---|---:|---|
| Turkce dental brans yonlendirme hedefi | `backend/app/clinical/data/metrics_report.json` | Sentetik dogruluk %96,7 | Golden sette bilerek zor vakalar var; cekimserlik bu nedenle onemli. |
| Kalibrasyon hedefi | `backend/app/clinical/data/metrics_report.json` | TEST ECE 0,0209 < 0,05 | "Kalibre guven" istem 2 icin teknik dayanak. |
| Acil vaka kacirmama kapisi | `backend/app/clinical/data/metrics_report.json` | 76/76 acil, kacis 0 | SaMD iddiasina donmeden, iletisim/yonlendirme guvenlik kapisi olarak yazilmali. |
| Cekimser/risk-kontrollu kabul | `backend/app/clinical/data/metrics_report.json` | Sentetik selective risk %0,85 | Dusuk guven ve belirsizlikte insana yukseltme ayirt edici unsur. |
| Yonetisim zarfi ihlal testi | `backend/app/governance/data/gate_report.json` | 160/160 senaryo, ihlal 0 | Tani, sinir-otesi isleyici, kimlik ve maskeleme kapilari ayrilmali. |
| Yerel kritik yol gecikmesi | `backend/app/perf/data/latency_report.json` | Saf kritik yol p95 ~0,72 ms | Local-first mimarinin teknik uygulanabilirligi icin destekleyici kanit. |
| Hekim karar suresi | `backend/app/learning/data/decision_time.json` | p95 22,64 sn < 30 sn | Shadow review is akisi ve optimizasyon iddiasi icin destek. |
| No-show risk modeli | `backend/app/learning/data/noshow.json` | TEST AUC 0,8301 | Bagimli istem: slot onerisi ve geri-cagirma zamanlamasi. |
| Mahremiyet-kapili etiket | `backend/app/learning/data/labels.json` | Redaksiyon kapisi + deterministik artefakt | Iddia: ham hasta metni egitim setine varsayilan olarak girmez. |
| Federe ogrenme fizibilitesi | `docs/IP-6.7-federe-ogrenme-fizibilite-notu.md` | Faz-2, onkosullu | Ana basvuruda opsiyonel embodiment veya devam basvurusu olarak konumlanabilir. |

## 4. Sekil Listesi

Vekile ve cizimciye verilecek sekil seti:

1. **Sistem mimarisi:** Hasta kanallari (WhatsApp/web/voice) -> local clinical
   orchestrator -> yonetisim zarfi -> hekim/operator -> randevu/PMS yazimi.
2. **Deterministik zarf akis diyagrami:** Veri sinifi -> risk kapilari ->
   sinir-otesi isleyici karari -> PII maskeleme -> audit izi -> otomatik gonderim
   veya insan incelemesi.
3. **Kalibre-cekimser triyaj:** Normalizer -> brans skoru -> kalibrasyon ->
   acil recall kapisi -> cekimserlik -> insan/otomatik yonlendirme.
4. **Hekim-onay ve ogrenme dongusu:** AI taslagi -> hekim onay/duzeltme/ret ->
   redaksiyon bekleyen etiket -> onayli egitim sinyali -> esik/yerel model guncelleme.
5. **No-show/slot/geri-cagirma bagimli akis:** No-show risk -> slot siralama ->
   riza + sessiz saat + cooldown kapilari -> proaktif geri-cagirma.
6. **Federe faz-2 opsiyonu:** Klinik ici yerel egitim -> secure aggregation ->
   merkezi ortak parametre -> kliniklere dagitim; ham veri hareket etmez.

## 5. Teknik Ayirt Edicilik Pozisyonu

**Patent vekiline onerilen vurgu:** Bulus, bir LLM sohbet botunu "daha zeki" yapmak
uzerine degil, modeli otomatik klinik iletisimde guvenli bicimde **daha sinirli ve
denetlenebilir** hale getirmek uzerinedir. Bu ters motivasyon su teknik etkileri
dogurur:

- Olasiliksal ciktilar her seferinde deterministik kapidan gecer.
- Ozel nitelikli verinin sinir-otesi islenmesi local-first modda yapisal olarak
  engellenir.
- Dusuk guven veya belirsiz brans kararinda otomasyon durur, insan devreye girer.
- Hekim geri bildirimi ham hasta metni olmadan ve redaksiyon kapisindan sonra
  ogrenme sinyaline donusur.
- PMS/HBYS yazimi, riza, slot, hekim incelemesi ve zarf kapilari gecilmeden
  tetiklenmez.

## 6. Vekile Sorulacak Net Sorular

1. Ana bulus ailesi tek basvuruda mi toplanmali, yoksa zarf/triyaj/ogrenme icin
   bolunmus basvuru stratejisi mi daha guclu olur?
2. Yazilim buluslari icin teknik etki argumani, "modeli sinirlayan deterministik
   klinik guvenlik zarfi" uzerinden yeterince savunulabilir mi?
3. SaMD riskini artirmadan acil-recall ve triyaj iddialari nasil formulle edilmeli?
4. Federe ogrenme varyanti ana basvuruya bagimli istem olarak mi, yoksa sonraki
   devam basvurusu olarak mi konumlanmali?
5. TURKPATENT/EPATS aramasinda hangi CPC/IPC siniflari ve anahtar kelimeler
   kapsama eklenmeli?
6. Kurucu ortak bulus sahipligi ve devir sozlesmeleri basvuru oncesi hangi sirayla
   tamamlanmali?

## 7. Basvuru Oncesi Temiz Oda Kontrol Listesi

- [ ] Vekil EPATS/Espacenet/Google Patents aramasini tamamlar.
- [ ] Novelty raporu, bilinen yakin sanat ve farklilasma tablosu ile guncellenir.
- [ ] Iddialar "tani koyma/tedavi onerme" gibi SaMD alanina tasacak dilden arindirilir.
- [ ] Sekiller 1-6 profesyonel patent cizimi formatina donusturulur.
- [ ] 3 bagimsiz istem + bagimli istem agaci vekil tarafindan yeniden yazilir.
- [ ] Bulus sahipleri ve hak devir belgeleri netlestirilir.
- [ ] Kamuya acik demo, pitch deck veya web iceriginde basvuru oncesi yeniligi
      bozabilecek teknik ayrinti paylasimi durdurulur.
- [ ] Basvuru sonrasi "patent pending" kullanimi icin marka/iletisim metni hazirlanir.

## 8. Paket Icindeki Dosyalar

Vekile gonderilecek minimum paket:

- `docs/patent/IP-6.4-6.5-novelty-ve-istem-taslaklari.md`
- `docs/patent/IP-6.6-vekil-basvuru-paketi.md`
- `docs/dental-ai-patent-dossier.md`
- `docs/IP-6.7-federe-ogrenme-fizibilite-notu.md`
- `backend/app/clinical/data/metrics_report.json`
- `backend/app/governance/data/gate_report.json`
- `backend/app/perf/data/latency_report.json`
- `backend/app/learning/data/labels.json`
- `backend/app/learning/data/thresholds.json`
- `backend/app/learning/data/decision_time.json`
- `backend/app/learning/data/noshow.json`
- `backend/app/learning/data/slots.json`
- `backend/app/learning/data/recall.json`

## 9. Karar

**IP-6.6 icin mevcut sonuc:** Teknik basvuru paketi hazir; resmi durum
**"vekil incelemesi bekliyor"**. Bu madde, dis patent vekili incelemesi yapilmadan
"tamamlandi" olarak isaretlenmemelidir. Buna ragmen repo tarafinda gereken teknik
girdi, kanit matrisi, istem omurgasi, sekil listesi ve soru seti hazirdir.
