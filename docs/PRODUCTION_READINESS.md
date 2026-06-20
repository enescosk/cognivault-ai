# CogniVault Production Readiness Gates

Bu belge “kod çalışıyor” ile “klinikte güvenle üretime çıkar” arasındaki farkı
ölçülebilir kapılara böler. Bir alan yalnız bütün zorunlu maddeleri kanıtlandığında
`ready` sayılır.

## 1. Kod içi sahiplik

### Klinik backend

- `clinical_service.py`: hasta/konuşma ingestion, kanal normalizasyonu, inbox ve erişim.
- `clinical_appointment_service.py`: hekim eşleme, takvim çakışması, randevu ve işlemler.
- `clinical_feedback_service.py`: doktor kararı, cevap farkı ve model-feedback kuyruğu.
- `clinical_pre_intake_service.py`: ön görüşme formu ve form-agent audit kaydı.
- `clinical_ai_service.py`: deterministik güvenlik zarfı ve sağlayıcı orkestrasyonu.

### Frontend

- `api/queryKeys.ts`: Dashboard ve klinik cache kimliklerinin tek kaynağı.
- `ClinicalPanel.tsx`: veri orkestrasyonu ve ekran kompozisyonu.
- `clinical/ClinicalPanelSections.tsx`: saf klinik görünüm bölümleri.
- `tokens.css` / `ui.css`: tema ve primitive katmanı.
- `patient.css` / `clinic-appointments.css`: ekran sahipli stiller.
- `global.css`: geriye uyumlu shell/eski ekranlar; yeni ekran stili kabul etmez.

## 2. Otomatik kalite kapıları

- Backend compile ve tüm pytest senaryoları geçer.
- Her backend testi temiz veritabanı şemasıyla başlar; sıra bağımlılığı yoktur.
- Alembic head ile ORM tablo paritesi korunur.
- Frontend unit test ve production TypeScript/Vite build geçer.
- Mobil TypeScript kontrolü geçer.
- CI aynı branch için eski koşuyu iptal eder ve salt-okunur repository izni kullanır.

## 3. Telefon altın akışı

Bir sürüm aşağıdakileri tek iz üzerinde kanıtlamalıdır:

1. Incoming çağrı CallSid ile açılır.
2. Birden çok konuşma turu aynı conversation'a, farklı idempotency anahtarlarıyla yazılır.
3. Yerel model kullanılamazsa güvenli deterministik cevap kalır.
4. OpenAI yalnız klinik politikası **ve hasta bazlı aktif cross-border rızası** birlikte varsa aday olur.
5. Riskli çıktı atanmış doktor inbox'ına hasta kimliğiyle düşer.
6. Doktor düzeltmesi kelime-diff'iyle `pending_redaction` feedback kaydı üretir.
7. Twilio status callback çağrı sonu/durum/süre bilgisini conversation metadata'sına yazar.
8. Ham ses feedback veya model-training tablosuna kopyalanmaz.

## 4. Kod dışında tamamlanması zorunlu kapılar

Bu maddeler repository testiyle “geçti” sayılamaz:

- KVKK metni, veri işleme dayanağı, açık rıza ve yurt dışı aktarım akışı uzman hukukçu tarafından yazılı onaylanır.
- Gerçek Twilio numarasıyla imza doğrulama açıkken en az 30 Türkçe çağrı; gürültü, aksan, tekrar, çağrı kopması ve gecikme ölçümü yapılır.
- En az bir klinikte resepsiyonist ve hekimle görev-tamamlama testi yapılır; kritik görevlerde başarı hedefi önceden sabitlenir.
- Gerçek HBYS/takvim adaptörü idempotency, çakışma ve rollback testlerinden geçer.
- Production PostgreSQL, yedekleme/geri-dönüş, secret yönetimi, alarm ve olay müdahale tatbikatı doğrulanır.

Bu dört grup tamamlanmadan ürün “production-ready” olarak sunulmaz; doğru ifade
“production-oriented pilot”tır.
