# CogniVault — Manuel Test Rehberi

Son güncelleme: 2026-07-15. Bu rehber, son sprintte eklenen her şeyi elle nasıl
doğrulayacağını adım adım anlatır. Otomatik kapı zaten var (`pytest` 5.100+ test);
bu rehber "gözünle gör" katmanıdır.

## 0. Ortamı ayağa kaldır

```bash
./scripts/run_backend.sh      # terminal 1 — uvicorn :8000, açılışta migrate+seed
./scripts/run_frontend.sh     # terminal 2 — vite :5173 (veya launch.json ile :5185)
```

Açılış logunda şunları GÖRMELİSİN (yoksa bir şey ters):
- `bootstrap_schema state=managed action=alembic_upgrade_head` → DB otomatik migrate oldu
- `voice_warmup whisper=ready` ve `voice_warmup piper=ready` → ses modelleri ısındı
- `Loading local Piper voice: ...tr_TR-fahrettin-medium.onnx` → doğal ses aktif

## 1. Hasta akışı (en kritik yol) — `http://localhost:5173/c/demo-klinik`

1. Sayfa **Türkçe açılmalı** (tarayıcın İngilizce olsa bile).
2. Alt bilgide "KVKK aydınlatma **v1**" yazmalı (eskiden "vv1" idi).
3. "AI ile randevu al" → KVKK onayı → sohbet açılır, karşılama sesli okunur
   (ilk ses ~0,5 sn içinde başlamalı — cümle cümle çalar).
4. Yaz: `Dişim çok ağrıyor, en kısa zamanda randevu almak istiyorum`
5. **Slot kartlarını kontrol et:**
   - Saatler mesai içinde olmalı (İstanbul 09:00–17:00, öğle arası yok)
   - Kronolojik sıralı olmalı (en erken önce)
   - Hekim adları gerçek takvimden gelmeli (Dt. Dr. Elif Kaya vb.)
6. Slot seç → isim + telefon ver → onay. Backend konsolunda
   `📱 SMS (SİMÜLASYON)` bloğunda **İstanbul saatiyle** randevu saati görünmeli.
7. Sayfayı yenile → kaldığın yerden devam etmeli (session resume).

## 2. Sesli görüşme — aynı sayfada 📞 düğmesi

1. "📞 Sesli görüşme"ye bas, mikrofon izni ver.
2. Konuş: "dişim ağrıyor randevu istiyorum".
3. Beklenenler:
   - Yanıt sesi **fahrettin** (dfki'den belirgin daha doğal; karşılaştırmak
     istersen `tmp/ses-karsilastirma/*.wav` dosyalarını dinle)
   - Tur arası bekleme öncekinden kısa (VAD kuyruğu 700 ms + warm-up + parçalı TTS)
   - "ağrıyor" gibi kelimeler doğru yazılmalı (alan sözlüğü ipucu aktif)
4. Ses kalitesini değiştirmek istersen: `.env` → `PIPER_VOICE_PATH` ile
   `tr_TR-fettah-medium.onnx` veya `tr_TR-dfki-medium.onnx` seçebilirsin.

## 3. Operatör paneli — `operator@cognivault.com / demo123`

1. Girişte üstte **sistem sağlık şeridi** görünmeli: LLM / Ses / **SMS** / Backend.
   - SMS pili "mock · Simülasyon" demeli (gerçek sağlayıcı bağlanınca "Gerçek gönderim")
   - Ollama kapalıysa LLM pili bunu göstermeli — sessiz düşüş yok artık
2. Az önce hasta akışında oluşturduğun randevu operatör listesinde görünmeli.
3. Hasta konuşması detayında ses telemetrisi (sağlayıcı, güven, retry) görünmeli.

## 4. Çoklu kiracı kanal eşlemesi (API ile)

```bash
# Eşleşmeyen numara strict modda reddedilir (varsayılan strict=false → default klinik)
# .env'e CLINICAL_CHANNEL_BINDING_STRICT=true ekleyip backend'i yeniden başlat:
curl -s -X POST http://localhost:8000/api/webhooks/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:%2B905321112233&To=whatsapp:%2B909999999999&Body=test"
# Beklenen: 202 "ignored_unbound_channel" — hiçbir kliniğe veri yazılmaz.
# Demo kliniğin bağlı numarası (+902120000000) ile gönderirsen 200 + mesaj işlenir.
```

## 5. Gerçek SMS'e geçiş (Netgsm hesabın olunca)

```bash
# .env:
SMS_PROVIDER=netgsm
NETGSM_USERCODE=...
NETGSM_PASSWORD=...
NETGSM_MSGHEADER=ONAYLIBASLIK
```
- Üçü de doluysa → hasta/doktor SMS'leri gerçek gider, sağlık şeridi "Gerçek gönderim" olur.
- Biri eksikse → uygulama ERROR loglar, mock'a düşer, `/health/ready` `sms: fail` döner
  ve şeritteki SMS pili kırmızı "Kimlik eksik — hasta SMS almıyor" gösterir. Sessiz kayıp yok.

## 6. Boş takvim / pilot modu

- Takvim 7 günlük **kayan pencere** ile her açılışta tamamlanır (Pazar hariç) —
  demo takvimi artık hiçbir zaman kurumaz.
- `.env` → `CLINICAL_DEMO_SLOTS_ENABLED=false` yaparsan (pilot modu): gerçek
  takvim boşken hastaya hayalî saat önerilmez, "ekip sizinle iletişime geçecek" akışı çalışır.
- Çifte rezervasyon testi: bir slotu onayladıktan sonra aynı slotu ikinci bir
  oturumdan onaylamaya çalış → 409 `slot_already_booked` almalısın.

## 7. Otomatik kapılar (her değişiklikten sonra)

```bash
cd backend && ./.venv/bin/python -m pytest -q      # tamamı yeşil olmalı
cd frontend && npx vitest run && npm run build     # 73+ test + build
cd backend && ./.venv/bin/python -m app.project_readiness  # fazlı hazırlık panosu
```
