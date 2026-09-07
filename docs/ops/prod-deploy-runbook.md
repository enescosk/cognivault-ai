# CogniVault — Production Dağıtım Runbook'u

> **Kapsam:** Tek sunucuya (VPS ya da klinik on-prem kutusu) sıfırdan canlı
> kurulum, günlük işletim ve geri dönüş. Yol haritasında **F3**.
>
> **Bu runbook'un sözü:** Runbook'u takip eden bir kişi, mühendislik desteği
> olmadan kurulumu bitirebilmeli. Bir adım "duruma göre değişir" diyorsa o adım
> henüz bitmemiştir.

## 0. Önkoşullar

| Gereksinim | Neden |
|---|---|
| Linux sunucu, 2+ çekirdek, 4 GB RAM, 40 GB disk | Postgres + 3 Python süreci + nginx + Caddy |
| Docker Engine 24+ ve Docker Compose v2 | Tüm servisler compose ile koşar |
| Alan adı (ör. `klinik.example.com`) | Caddy sertifikayı buna alır; **Twilio imzası da bu URL'e göre doğrulanır** |
| DNS A kaydı → sunucunun public IP'si | Let's Encrypt HTTP-01 doğrulaması için |
| 80 ve 443 portları dışarıya açık | Sertifika alımı 80'i, trafik 443'ü kullanır |

> ⚠️ **Yerel LLM (opsiyonel).** Sunucuda Ollama/vLLM yoksa `.env.prod`'da
> `PREFERRED_LLM_PROVIDER=local` ve `LOCAL_LLM_BASE_URL=` boş bırakın. Bu
> profilde sistem deterministik motorla çalışır — triyaj kararları zaten
> deterministik, kayıp yalnız cevap üslubunun doğallığındadır. `auto` bırakırsanız
> ve OpenAI anahtarı varsa sistem buluta düşmeye çalışır; KVKK açısından bilinçli
> bir tercih değilse `local` bırakın.

## 1. Kurulum (ilk dağıtım)

```bash
git clone <repo> cognivault && cd cognivault
cp .env.prod.example .env.prod
```

`.env.prod`'u doldurun. Sırları **üretin, uydurmayın**:

```bash
openssl rand -base64 48   # JWT_SECRET
openssl rand -base64 32   # POSTGRES_PASSWORD
```

Zorunlu alanlar: `COGNIVAULT_DOMAIN`, `ACME_EMAIL`, `JWT_SECRET`,
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.

Dağıtımdan **önce** kapıları koşun (hiçbir konteyner başlatmaz):

```bash
./scripts/prod/deploy.sh --check-only
```

Sonra tam dağıtım:

```bash
./scripts/prod/deploy.sh
```

Script şu sırayla ilerler ve **herhangi bir adım düşerse durur**:

1. `.env.prod` var mı, zorunlu alanlar dolu mu, `JWT_SECRET` ≥32 karakter mi
2. Config denetimi — `python -m app.ops.preflight --check-env`
3. İmajlar derlenir
4. `alembic upgrade head` (tek seferlik `migrate` servisi)
5. Servisler başlar
6. `/readyz` yeşile dönene kadar beklenir (90 sn)
7. Duman testi (`scripts/prod/smoke_test.sh`)

> **Neden config denetimi konteynerlerden önce:** Yanlış config'i canlıya alıp
> sonra geri dönmektense, hiç almamak. Denetim uygulamanın kendi guard kodunu
> koşar (`app/ops/preflight.py`) — script ile production davranışı arasında
> ikinci bir doğruluk kaynağı oluşmasın diye.

## 2. Dağıtım sonrası — klinik provizyonu

```bash
CV="docker compose -f docker-compose.prod.yml --env-file .env.prod"

# 1) Kliniği tek komutla provizyonla (idempotent)
$CV exec backend python -m app.onboarding.provision --help

# 2) Telefon numarasını kliniğe bağla (F1 — gerçek +90 hattı)
$CV exec backend python -m app.ops.bind_channel --clinic <slug> --phone "+90312XXXXXXX"
$CV exec backend python -m app.ops.bind_channel --list

# 3) İlk yedek provasını elle doğrula
$CV exec backend python -m app.ops.backup drill
```

> `CLINICAL_CHANNEL_BINDING_STRICT=true` olduğu için **bağlanmamış bir numaradan
> gelen çağrı reddedilir** ve default kliniğe düşmez. Adım 2 atlanırsa hasta
> "bu numara şu anda hizmet dışıdır" duyar. Bu kasıtlı: çok kiracılı kurulumda
> yanlış kliniğe veri yazmaktansa çağrıyı reddetmek yeğdir.

## 3. Güncelleme (mevcut kurulum üzerine yeni sürüm)

```bash
git pull
./scripts/prod/deploy.sh
```

Aynı script güncellemede de doğru davranır: migration'ı yeniden koşar (alembic
idempotenttir), imajları yeniden derler, servisleri yeniler ve duman testiyle
biter. **Güncellemeden önce yedek alın** (Bölüm 5).

## 4. Servis haritası

| Servis | Görev | Host portu |
|---|---|---|
| `caddy` | TLS sonlandırma, tek domain yönlendirme | 80, 443 |
| `frontend` | SPA (nginx statik) | — |
| `backend` | API + webhook'lar + sağlık probları | — |
| `outbox-worker` | Giden SMS/webhook kuyruğu (retry + dead-letter) | — |
| `migrate` | Tek seferlik `alembic upgrade head` | — |
| `db` | PostgreSQL 16 | — (host'a **kapalı**) |
| `backup` | Günlük yedek **provası** | — |

Domain altındaki yollar: `/api/*`, `/healthz`, `/readyz`, `/health*` → backend;
diğer her şey → SPA. `/metrics` **dışarıya kapalı** (istek hacmi ve klinik
kimliği sızdırır); iç ağdan `http://backend:8000/metrics` ile scrape edilir.

## 5. Yedekleme ve geri dönüş

`backup` servisi günde bir **prova** koşar — sadece yedek almaz, geri
dönülebildiğini kanıtlar: yedekle → bütünlük doğrula → geçici hedefe geri yükle
→ satır sayılarını karşılaştır.

```bash
CV="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$CV exec backend cat data/backups/latest.json   # "overall_ok": true olmalı
$CV logs --tail 50 backup                       # son prova log'u
$CV exec backend python -m app.ops.backup backup  # elle yedek (güncelleme öncesi)
```

> **"Yedeğimiz var" cümlesi ancak `overall_ok: true` iken kurulabilir.**
> `false` görürseniz bu bir uyarı değil, olaydır — Bölüm 8'e gidin.

PostgreSQL'de geri yükleme yeni veritabanı yaratma yetkisi istediği için
otomatik değildir; prova `pg_restore --list` ile yapı doğrulaması yapar. Gerçek
geri yükleme:

```bash
$CV stop backend outbox-worker          # yazan süreçleri durdur
$CV exec db pg_restore --clean --if-exists -U <user> -d <db> /path/to/backup
$CV start backend outbox-worker
./scripts/prod/smoke_test.sh
```

## 6. Günlük sağlık kontrolü

```bash
CV="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$CV ps                                   # hepsi Up / healthy olmalı
./scripts/prod/smoke_test.sh             # 8 kontrol, hepsi PASS
$CV exec backend cat data/backups/latest.json | head -20
```

Operatör/admin token'ıyla kuyruk sağlığı:

```
GET /api/agents/outbox/summary
GET /api/agents/outbox/events?status=dead_letter
```

Dead-letter **boş olmalı**. Dolu ise bir hastaya gitmesi gereken SMS gitmemiş
demektir — sessiz bir hata değil, müdahale sebebidir.

## 7. Geri dönüş (rollback)

Dağıtım duman testinde düştüyse servisler **ayakta bırakılır** ki
inceleyebilesiniz. Karar ağacı:

| Belirti | Yapılacak |
|---|---|
| `/readyz` 503 | DB ayakta mı: `$CV ps db`, `$CV logs db`. Migration yarım kalmışsa Bölüm 5'ten geri yükle. |
| `/api/*` 502 | Backend çökmüş: `$CV logs --tail 100 backend`. Genelde eksik/hatalı env değeri. |
| `/api/*` 404 | Caddy yönlendirmesi bozuk: `deploy/Caddyfile` ve `$CV logs caddy`. |
| TLS doğrulanamıyor | DNS A kaydı ve 80 portu. `$CV logs caddy` sertifika hatasını yazar. |
| Yeni sürüm bozuk, eski çalışıyordu | `git checkout <önceki-tag> && ./scripts/prod/deploy.sh` |

> ⚠️ **Migration geri alınamaz varsayın.** Alembic downgrade her migration için
> yazılmış olmayabilir. Şema değişikliği içeren bir sürüme geçmeden önce yedek
> alın (Bölüm 5); geri dönüş yolu downgrade değil, **yedekten geri yükleme**dir.

## 8. Olay müdahalesi

| Olay | İlk hamle |
|---|---|
| Yedek provası `overall_ok: false` | `$CV logs backup`. Düzelene kadar **şema değiştiren dağıtım yapma**. |
| Dead-letter kuyruğu doluyor | `GET /api/agents/outbox/events?status=dead_letter` — sağlayıcı (Netgsm/Twilio) kimlik bilgileri ve kotası. |
| Telefon çağrıları reddediliyor | `bind_channel --list` — numara bağlı ve aktif mi. |
| Hasta verisi yurt dışına gitti şüphesi | `PREFERRED_LLM_PROVIDER` ve `CLINICAL_EXTERNAL_AI_ALLOWED` değerlerini kontrol edin; sınır-ötesi işlem hem klinik izni hem hasta açık rızası ister. |
| Sertifika yenilenemedi | `$CV logs caddy`. 80 portu kapanmış olabilir. Sertifikalar 30 gün önceden yenilenir, panik payı vardır. |

## 9. Bu runbook'un henüz kanıtlamadığı şeyler

Dürüstlük bölümü — aşağıdakiler kod ile değil, **saha ile** kapanır:

- [ ] Gerçek bir sunucuda uçtan uca kurulum kronometreyle koşulmadı (hedef <6 saat).
- [ ] Gerçek bir domain üzerinde Let's Encrypt sertifikası alınmadı.
- [ ] PostgreSQL'de gerçek geri yükleme (Bölüm 5) canlı veriyle denenmedi — RPO/RTO ölçülmedi.
- [ ] Secret rotation (JWT + DB + webhook token) tatbikatı yapılmadı.
- [ ] Alarm/izleme (`/metrics` scrape + eşikler) kurulmadı — `/metrics` hazır, tüketici yok.

Bunlar F3'ün **saha ayağı**; F4 pilot kliniğiyle birlikte kapanır.
