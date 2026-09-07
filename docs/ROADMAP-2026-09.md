# CogniVault — Yol Haritası (2026-09-05'ten itibaren)

> Bu dosya `docs/BIGG_AKSIYON_PLANI.md`'nin yerine geçmez; onu **sıraya** koyar.
> BiGG planı "hangi iş paketi ne vaat etti"yi tutar, bu dosya "sırada ne var"ı tutar.
>
> Durum etiketleri: `⬜ AÇIK` · `🔵 ŞU AN` · `🟡 DEVAM` · `✅ YAPILDI`

## Tek cümlelik durum

Ar-Ge çekirdeği (triyaj, yönetişim zarfı, öğrenme döngüsü, ses kontrol mantığı,
ops araçları) **bitmiş ve panolu kanıtlı** — 93/93 kapı, 5170 backend + 73
frontend testi. Eksik olan tek şey **gerçek dünya teması**: sistemi hiç kimse
gerçek bir telefondan aramadı, hiçbir klinik canlıda kullanmadı.

## Yol haritasının tek ilkesi

Bundan sonraki her faz, **gerçek bir insanın gerçek bir kliniğe randevu
almasına** bir adım daha yaklaştırmalı. Yeni pano, yeni kanıt dosyası, yeni
soyutlama — hiçbiri bu ilkenin önüne geçmez.

---

## F0 — Temizlik ve Doğruluk ✅ YAPILDI (2026-09-05)

Bunlar bitmeden diğer fazlar yalan söyler: testler kırmızı, CI kopuk, main kirli.

- ✅ **0.1 KVKK rıza deliğini kapat.** (branch `fix/f0-kvkk-consent-ve-test-hizi`) `clinical_ai_service._try_runtime_reply`
  yalnızca **klinik politikasına** (`external_transfer_allowed`) bakıyor,
  **hastanın kendi rızasına** (`external_ai_consent`) bakmıyor; ana sağlayıcı
  yolu ise `politika AND rıza` diye hesaplıyor. Runtime yolu önce çalıştığı için
  rıza kapısı devre dışı kalıyor. `PREFERRED_LLM_PROVIDER=auto` (varsayılan) ve
  lokal LLM yokken bu, hasta metnini rızasız OpenAI'a gönderir.
  - ✅ `app/ai/runtime.py:runtime_is_cross_border()` eklendi; `_try_runtime_reply`
    artık `external_ai_consent` alıyor ve sınır-ötesi runtime'da rıza yoksa yolu
    kapatıyor. Lokal runtime'da rıza aranmıyor → yerel-öncelik davranışı aynı
    (sadece daraltma, genişleme yok). 3 regresyon testi eklendi.
- ✅ **0.2 Test paketini hızlandır — 65:19 → 3:11.** Testler gerçek
  Ollama'ya (`localhost:11434`) HTTP atıyor. `conftest.py`'ye ağ kill-switch'i:
  test ortamında dış/lokal LLM çağrısı **varsayılan kapalı**, açıkça isteyen test
  fixture ile açar.
  - ✅ `tests/conftest.py`'de iki katmanlı kill-switch: sağlayıcı ayarları
    boşaltıldı + `socket.socket.connect` kapatıldı (kaçış kapısı:
    `allow_real_network` fixture'ı). Tüm paket kill-switch ile yeşil
    (**5203 passed, 1 skipped, 3:11**) → hiçbir test gerçek ağa muhtaç değilmiş.
- ✅ **0.3 CI'ı gerçekten yeşile al.** `.github/workflows/ci.yml` backend job'ı
  `timeout-minutes: 15` — 65 dakikalık paketle CI zaten geçemiyor. 0.2 sonrası
  gerçek bir GitHub Actions koşusuyla doğrula.
  - ✅ Lokalde CI'ın üç job'ı da geçiyor: `compileall` OK · `pytest -q` 3:11
    (limit 15 dk) · `npm run test:run` 73/73 · `npm run build` OK.
  - ✅ Gerçek koşum doğrulandı — [run 33998544123](https://github.com/enescosk/cognivault-ai/actions/runs/33998544123):
    Backend 5m58s ✓ · Frontend 20s ✓ · Mobile typecheck 18s ✓.
  - İlk koşum (33990721991) backend'de kırmızıydı ve **önceden var olan** bir
    hatayı ortaya çıkardı: `math` tabanlı ECE metrikleri libm farkı yüzünden
    platformlar arasında son bitte kayıyor, commit'lenmiş kanıt artefaktı `==`
    karşılaştırmasını geçemiyordu (macOS `0.24808362369337983` vs Linux
    `...97`). Yani artefakt üretildiği makineye bağımlıydı ve CI hiç yeşil
    olamazdı. `app/core/determinism.py:stabilize_floats()` eklendi, artefakt
    9 basamağa yuvarlanarak yeniden üretildi; kapı kararları yuvarlanmamış
    değerlerle verilmeye devam ediyor.
  - ✅ **Kalan risk kapatıldı (2026-09-07, branch `fix/artifact-determinism`).**
    24 commit'li artefaktın taranmasıyla riskin 17 değil **5 dosyada** olduğu
    görüldü; beşi de yuvarlandı ve artık **0/24** yuvarlanmamış float var.
    Asıl kalıcı çözüm tek tek yama değil, `tests/test_determinism.py`'deki
    parametrize kapı: `app/**/*.json` altındaki HER artefakt taranıyor, yeni bir
    pano `stabilize_floats` olmadan eklenirse test o dosyanın adıyla düşüyor.
- ✅ **0.4 main'i temizle.** `app/ops/bind_channel.py` ve
  `docs/ops/netgsm-twilio-sip-trunk-kurulumu.md` commit'lendi. CLI'a 5 test
  eklendi (bağlama+resolver eşleşmesi, idempotent yeniden yönlendirme, devre dışı
  bırakma, hatalı slug reddi, kanalın anahtarın parçası olması) — yanlış bağlanan
  bir numara çağrıyı yanlış kliniğe yazar, resolver kadar kritik.
- ✅ **0.5 `origin/main` ile birleştir.** Yerel main ve `origin/main` ayrışmıştı;
  `201cfde` (İP-6.1 başarı-bazlı faturalama MVP'si) merge edildi, paket birleşik
  halde yeşil.

---

## F1 — Gerçek Telefon Hattı (asıl kilit; ~1 hafta)

Kod tarafı **hazır**: `phone_flow_service.py` çok turlu slot akışını telefonda
kapatıyor, kendi TTS'imizi `<Play>` ile veriyor, KVKK anonsu var, onay SMS'i
Netgsm'den gidiyor. Eksik olan tek şey **arayabileceğimiz bir +90 numara**.

- ⬜ **1.1** Netgsm SIP Trunk + coğrafi +90 numara aktivasyonu.
- ⬜ **1.2** Twilio SIP Domain + Netgsm IP ACL (yol: `docs/ops/netgsm-twilio-sip-trunk-kurulumu.md`).
- ⬜ **1.3** Backend public HTTPS (test: ngrok · prod: gerçek domain + TLS);
  `CLINICAL_WEBHOOK_BASE_URL` imzayla birebir eşleşmeli.
- ⬜ **1.4** `python -m app.ops.bind_channel --clinic <slug> --phone "+90..."` +
  `CLINICAL_CHANNEL_BINDING_STRICT=true`.
- ⬜ **1.5** **İlk gerçek arama.** Kayıt al, gecikmeleri ölç.

**Kabul kapısı (F1 kapanır):** Bir insan telefonu eline alıp numarayı arıyor,
konuşuyor, **90 saniye içinde** onay SMS'i geliyor ve randevu operatör panelinde
slot'a bağlı olarak görünüyor. Elle müdahale yok.

> KVKK notu: Bu yol (Yol A) sesi Twilio ABD STT'sinden geçirir → sınır-ötesi
> işlemci sorunu **devam eder**. Pilot sözleşmesinde bu açıkça yazılmalı; kalıcı
> çözüm Yol B (Netgsm-native + lokal Whisper) ve F5'e bağlı.

---

## F2 — Gerçek Cihaz / Gerçek Ses QA (~3-4 gün)

`docs/voice-qa/real-device-qa.md` matrisi ve panele kayıt girme akışı hazır;
**koşulmadı**.

- ⬜ **2.1** 12 senaryo: iPhone Safari/Chrome, Android Chrome, kablolu/BT kulaklık,
  hoparlör, sessiz oda, resepsiyon gürültüsü, hızlı konuşma, duraklama, kendini
  düzeltme, yanlış telefon numarası, acil vaka, saçma girdi.
- ⬜ **2.2** Her senaryo için: mikrofon izni süresi, ilk sese kadar süre, STT
  doğruluğu, retry sayısı, 60 sn altı tamamlama, randevu oluştu mu, operatör
  müdahalesi gerekti mi.
- ⬜ **2.3** Bloke/major hatalar → tekrar-üretim adımlı ticket.

**Kabul:** 12 kayıt panele girilmiş, pilot dashboard'daki QA kapısı yeşil, acil
vaka ve randevu onayı davranışında **regresyon yok**.

---

## F3 — Tek Kliniğe Kurulabilir Ürün 🟡 KOD AYAĞI BİTTİ (2026-09-07)

Branch: `feat/f3-prod-deploy`. Kod ve yapılandırma ayağı tamam; **saha ayağı**
(gerçek sunucu, gerçek domain, kronometre) F4 pilotuyla kapanır.

Yolda iki gerçek engel çıktı, ikisi de düzeltildi:
- **`/readyz` veritabanı ölüyken bile HTTP 200 dönüyordu** — gövdede `"fail"`
  yazıyor ama durum kodu 200 olduğu için yük dengeleyici / Docker healthcheck
  konteyneri SAĞLIKLI görüp trafik göndermeye devam ederdi. Artık 503.
- **Backend imajında `migrations/` ve `alembic.ini` yoktu** — production'da şema
  açık `alembic upgrade head` ile değişiyor ama migration'lar imaja
  kopyalanmadığı için bu komut konteynerde hiç koşamazdı. Yani mevcut imajla
  production'a çıkmak fiilen imkânsızdı.

- ✅ **3.1** `docker-compose.prod.yml` + `deploy/Caddyfile` (otomatik Let's
  Encrypt TLS, tek domain: `/api/*` → backend, gerisi → SPA, `/metrics` dışarıya
  kapalı) + `.env.prod.example`. Postgres host'a port açmıyor; sırların
  varsayılanı yok (`${VAR:?}`); backend `migrate` bitmeden başlamıyor.
- ✅ **3.2** `docs/ops/prod-deploy-runbook.md` — kurulum, provizyon, güncelleme,
  yedek/geri dönüş, günlük sağlık kontrolü, rollback karar ağacı, olay
  müdahalesi. `scripts/prod/deploy.sh` (kapılı: env → config denetimi → derleme →
  migration → başlatma → `/readyz` → duman testi; `--check-only` hiçbir konteyner
  başlatmaz) ve `scripts/prod/smoke_test.sh` (8 dış kontrol).
- ✅ **3.3** Operasyon otomasyonu: günlük yedek **provası** servisi (yedekle →
  doğrula → geri yükle → karşılaştır), outbox worker servisi, `/readyz` tabanlı
  konteyner healthcheck'i, `preflight --check-env` ile canlı config denetimi.
- ✅ **3.5** Dağıtım paketi test altında — `tests/test_prod_deploy_package.py`
  (27 test) compose/Caddyfile/Dockerfile/env örneğinin kodla senkron kalmasını
  garantiliyor. Bu dosyalar aksi hâlde hiç test edilmiyordu.
- ⬜ **3.4** `python -m app.onboarding.provision`'ı **gerçek klinik verisiyle
  kronometreyle** koş → İP-6.3'ün "<1 gün onboarding" iddiası kanıtlanır.
  (Gerçek klinik verisi gerektirir — F4'e bağlı.)

**Kalan kabul kapıları (saha):** gerçek sunucuda kronometreli kurulum (<6 saat),
gerçek domain'de sertifika alımı, canlı veriyle geri yükleme (RPO/RTO ölçümü),
secret rotation tatbikatı, alarm/izleme kurulumu. Runbook Bölüm 10 bunları
dürüstçe "henüz kanıtlanmadı" olarak listeliyor.

---

## F4 — Pilot Klinik (İP-5.3–5.6 · ~30 gün saha)

Satış paketi (`docs/sales/`), launch pack (`docs/pilot/IP-5.1-*`), fiyatlama
(`docs/commercial/IP-6.1-*`), KVKK dosyaları hazır — **imza yok**.

- ⬜ **4.1** 3-5 klinikle görüşme (intake formu + pilot teklifi ile).
- ⬜ **4.2** 1 imza: sözleşme + KVKK aydınlatma/açık rıza metinleri + veri işleyen
  sözleşmesi.
- ⬜ **4.3** Canlı kurulum (F3 runbook'u) + personel eğitimi.
- ⬜ **4.4** 30 gün saha + haftalık iterasyon döngüsü.
- ⬜ **4.5** Saha kalibrasyon raporu: KPI panosu **gerçek veriyle** dolu
  (randevu başarısı ≥%70, 60 sn altı ≥%50, STT retry ≤%20, operatör müdahalesi
  ≤%25, güvenlik olayı = 0).
- ⬜ **4.6** ≥3 referans yazısı.

**Kabul:** ≥%85 memnuniyet · sıfır güvenlik-kapısı ihlali · go/no-go kararı
veriden alınabiliyor.

---

## F-ARA — Bayat kalibratör kararı (küçük ama İP-1'i etkiler)

2026-09-07'de artefakt determinizmi çalışırken çıktı: `calibration.json` ve
`selective.json` commit'li hâlleriyle **bayat**. Aynı korpustan yeniden fit
edildiklerinde fitter farklı bir kalibratör üretiyor:

```
commit'li : thresholds [0, 4, 5, 6, 7]      values[0] = 0.9876543209876543
yeniden fit: thresholds [0, 1, 4, 5, 6, 7]  values[0] = 0.784615385  (+ 0.984555985)
```

Bu artefaktlar **çalışma zamanında yükleniyor** (`normalizer.py` kalibratörü,
`report.py`/`selective.py` eşiği), yani canlı güven kalibrasyonunu etkiliyorlar.
Determinizm işine karıştırılmadı — o iş 1e-10'luk bir yuvarlamayken bu gerçek bir
davranış değişikliği ve İP-1'in (kalibre çekimser yönlendirici) sahibinin kararı.

- ⬜ Fitter mi değişti, korpus mu? `git log` ile artefaktın en son ne zaman
  üretildiğini ve o tarihten sonra `calibration.py`/korpusun değişip değişmediğini
  belirle.
- ⬜ Yeniden fit edilmiş kalibratörle İP-1 kapılarını koş (ECE, seçici risk,
  acil-recall). Panodaki metrikler değişmiyordu ama canlı yol farklı.
- ⬜ Karar verildikten sonra bu iki dosyaya da **tazelik testi** ekle — şu an
  hiçbir test onları üreticiyle karşılaştırmıyor, bayatlamaları bu yüzden
  aylarca görünmedi.

## F5 — İP-3.6: Fine-tune Kararını Kapat (~2-3 gün, F1'e paralel)

Üç GPU denemesi de başarısız (v1 acil-recall %26,7 · v2 %13,3 · v3 validation %0).
Bu **kapatılması gereken bir karar**, sürüncemede bırakılacak bir iş değil.

Üç seçenek — birini seç, BiGG raporuna yaz:
- **(A) Negatif bulgu olarak kapat.** "Bu veri ölçeğinde küçük model triyaj
  sınıflandırmasında genellemedi; deterministik motor birincil karar
  mekanizmasıdır" + yumuşatılamaz `emergency_recall_pass` kapısı bilimsel çıktı
  olarak sunulur. **Önerilen.**
- **(B) Kapsamı daralt.** Modeli **sınıflandırma için değil**, yalnızca
  üslup/NLG (cevabın doğallığı) için fine-tune et; triyaj kararı deterministik
  kalır. Güvenlik riski sıfıra yakın, kazanç "robotik değil" hissi.
- **(C) Veriyi büyüt.** 581 örnek çok az; F4 pilotundan gelen gerçek etiketli
  veriyle (İP-4.2 mahremiyet-kapılı etiket döngüsü) tekrar dene. **F4'ten önce
  yapılamaz.**

**Kabul:** Seçim yapılmış, gerekçesi ve kanıtı `docs/BIGG_AKSIYON_PLANI.md`'ye
işlenmiş.

---

## F6 — Ticarileşme ve FM (İP-6.1 / 6.4-6.6 / 6.8)

- 🟡 **6.1** Billing MVP — `app/billing/success_billing.py` (başarı-bazlı
  faturalama motoru + 193 test) `origin/main`'de landed. Kalan: gerçek plan/fiyatla
  bağlama ve fiyatın pilot ödeme istekliliğiyle valide edilmesi (F4'e bağlı).
- ⬜ **6.2** Patent: `docs/patent/IP-6.6-vekil-basvuru-paketi.md`'yi **gerçek
  vekile** teslim et, resmî novelty araştırması yaptır.
- ⬜ **6.3** ≥5 ücretli klinik dönüşümü.

---

## Sıralama gerekçesi (neden bu sırayla?)

1. **F0 önce**, çünkü kırmızı test + kopuk CI ile ilerleyen her şey ölçülemez —
   ve 0.1 gerçek bir KVKK açığı, pilot öncesi kapanmak zorunda.
2. **F1 ikinci**, çünkü telefon akışı kodu bitmiş durumda ve tek eksik dış
   bağımlılık (numara) tedarik süresi olan bir şey — erken başlat.
3. **F2 ve F3 paralel yürüyebilir**; ikisi de F4'ün ön koşulu.
4. **F4 en uzun süren ve en çok dış bağımlılığı olan iş** — klinik görüşmelerini
   F1 devam ederken başlat, teknik hazır olduğunda imza hazır olsun.
5. **F5 arka planda** kapanır; F6 pilot verisi olmadan anlamsız.

## Değişiklik Günlüğü

- **2026-09-07 (ii)** — Artefakt determinizmi kapatıldı: 5 üretici yuvarlandı +
  tüm artefaktları tarayan parametrize kapı eklendi. Yolda **`calibration.json`
  ve `selective.json`'ın bayat olduğu** ortaya çıktı (fitter artık farklı bir
  kalibratör üretiyor) — bu bir davranış değişikliği olduğu için determinizm
  işine karıştırılmadı, ayrı karar olarak açık bırakıldı (bkz. F5 altındaki not).
- **2026-09-07** — F3'ün kod ayağı bitti (`feat/f3-prod-deploy`). Prod compose +
  Caddy TLS + kapılı deploy script'i + duman testi + runbook + 27 sözleşme
  testi. Yolda `/readyz`'in 503 dönmediği ve imajda migration bulunmadığı
  ortaya çıktı, ikisi de düzeltildi. Sıradaki: **F1 — gerçek +90 telefon hattı**
  (numara tedariki bekliyor).
- **2026-09-06** — F0 **tamamen** kapandı: CI gerçek koşumla yeşil doğrulandı
  (33998544123). Yol boyunca commit'lenen kanıt artefaktlarının platforma bağımlı
  olduğu ortaya çıktı ve düzeltildi.
- **2026-09-05 (akşam)** — F0'ın ilk dört maddesi. KVKK rıza açığı düzeltildi, test paketi
  65:19'dan 3:11'e indi, F1 ön koşulları (bind_channel CLI + SIP dokümanı) test
  edilip commit'lendi, `origin/main` merge edildi. Sıradaki: **F1 — gerçek +90
  telefon hattı.**
- **2026-09-05** — Yol haritası sıfırdan oluşturuldu. Tespit: 93/93 teknik kapı
  geçiyor ama gerçek dünya teması sıfır; 2 kırmızı test gerçek bir KVKK rıza
  açığını gösteriyor; test paketi 65 dk sürüyor ve CI 15 dk limitiyle geçemez.
