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
  - ⚠️ **Kalan risk:** aynı sınıf 17 `test_committed_artifact_is_fresh` testinde
    daha var (özellikle exp/log kullanan no-show lojistik regresyonu). Şimdilik
    yalnızca fiilen kırılan düzeltildi; diğerleri farklı bir platformda/Python
    sürümünde patlayabilir. Sırası geldiğinde `stabilize_floats` tüm üreticilere
    uygulanmalı.
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

## F3 — Tek Kliniğe Kurulabilir Ürün (~1 hafta)

Bugün elimizde sadece geliştirici `docker-compose.yml` var. Bir kliniğe kurulacak
şey yok.

- ⬜ **3.1** `docker-compose.prod.yml` + reverse proxy + TLS + gerçek domain.
- ⬜ **3.2** Dağıtım runbook'u: migration → preflight (`app.ops.preflight`) →
  seed → smoke test → geri dönüş adımı.
- ⬜ **3.3** Operasyon otomasyonu: günlük yedek cron (`scripts/backup_db.sh`),
  haftalık geri-dönüş provası (`scripts/backup_drill.sh`), outbox worker servisi,
  `/readyz` izleme.
- ⬜ **3.4** `python -m app.onboarding.provision`'ı **gerçek klinik verisiyle
  kronometreyle** koş → İP-6.3'ün "<1 gün onboarding" iddiası kanıtlanır.

**Kabul:** Sıfır makinede, runbook'u takip eden bir kişi <6 saatte kurulumu
bitiriyor; geri-dönüş provası `overall_ok: true` veriyor.

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
