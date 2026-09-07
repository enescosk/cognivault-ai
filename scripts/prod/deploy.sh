#!/usr/bin/env bash
# CogniVault production dağıtımı — tek komut, kapılı.
#
#   ./scripts/prod/deploy.sh              → tam dağıtım
#   ./scripts/prod/deploy.sh --check-only → sadece dağıtım öncesi kapıları koş
#
# Sıra kasıtlı: HİÇBİR konteyner ayağa kalkmadan önce config denetlenir.
# Yanlış config'i canlıya alıp sonra geri dönmek yerine, hiç almamak.
#
#   1. .env.prod var mı, zorunlu alanlar dolu mu
#   2. Config denetimi (app.ops.preflight --check-env) — zayıf JWT, sqlite,
#      wildcard CORS gibi bulgular dağıtımı BLOKLAR
#   3. İmajları derle
#   4. Şema göçü (alembic upgrade head) — tek seferlik migrate servisi
#   5. Servisleri başlat
#   6. /readyz yeşile dönene kadar bekle
#   7. Duman testi
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env.prod"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE")
CHECK_ONLY=0
[[ "${1:-}" == "--check-only" ]] && CHECK_ONLY=1

step() { printf '\n=== %s ===\n' "$1"; }
die()  { printf '\nHATA: %s\n' "$1" >&2; exit 1; }

# ── 1. Ortam dosyası ─────────────────────────────────────────────────────────
step "1/7  Ortam dosyası"
[[ -f "$ENV_FILE" ]] || die ".env.prod yok. Önce: cp .env.prod.example .env.prod && düzenle"

missing=()
for key in COGNIVAULT_DOMAIN ACME_EMAIL JWT_SECRET POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
  value="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
  [[ -z "$value" ]] && missing+=("$key")
done
[[ ${#missing[@]} -gt 0 ]] && die ".env.prod içinde boş zorunlu alan(lar): ${missing[*]}"

JWT_VALUE="$(grep -E '^JWT_SECRET=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
[[ ${#JWT_VALUE} -lt 32 ]] && die "JWT_SECRET 32 karakterden kısa. Üret: openssl rand -base64 48"
echo "  OK — zorunlu alanlar dolu, JWT_SECRET yeterli uzunlukta"

# ── 2. Config denetimi ───────────────────────────────────────────────────────
# Guard'ları uygulamanın KENDİ kodundan koşuyoruz: bu script ile production
# davranışı arasında ikinci bir doğruluk kaynağı oluşmasın.
step "2/7  Dağıtım öncesi config denetimi"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  ( set -a; . "$ENV_FILE"; set +a; cd "$ROOT_DIR/backend" && ./.venv/bin/python -m app.ops.preflight --check-env ) \
    || die "Config denetimi dağıtımı blokladı (yukarıdaki BLOCK satırlarına bakın)"
else
  echo "  Yerel venv yok — denetim geçici konteynerde koşuyor"
  "${COMPOSE[@]}" run --rm --no-deps --entrypoint python backend -m app.ops.preflight --check-env \
    || die "Config denetimi dağıtımı blokladı"
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  printf '\n--check-only: kapılar geçildi, dağıtım yapılmadı.\n'
  exit 0
fi

# ── 3. İmajlar ───────────────────────────────────────────────────────────────
step "3/7  İmajlar derleniyor"
"${COMPOSE[@]}" build

# ── 4. Şema göçü ─────────────────────────────────────────────────────────────
# Göç ayrı ve önce: yarı göçmüş şemayla trafik almaktansa hiç başlamamak yeğdir.
step "4/7  Veritabanı şeması (alembic upgrade head)"
"${COMPOSE[@]}" up -d db
"${COMPOSE[@]}" run --rm migrate || die "Migration başarısız — hiçbir servis başlatılmadı, veri değişmedi"

# ── 5. Servisler ─────────────────────────────────────────────────────────────
step "5/7  Servisler başlatılıyor"
"${COMPOSE[@]}" up -d

# ── 6. Hazırlık beklemesi ────────────────────────────────────────────────────
step "6/7  Backend hazır olana kadar bekleniyor"
ready=0
for attempt in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T backend python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=4).status == 200 else 1)" \
      >/dev/null 2>&1; then
    ready=1
    echo "  OK — /readyz yeşil (deneme $attempt)"
    break
  fi
  sleep 3
done
if [[ "$ready" -ne 1 ]]; then
  echo "  Backend hazır olmadı. Son log'lar:" >&2
  "${COMPOSE[@]}" logs --tail 60 backend >&2 || true
  die "Backend /readyz yeşile dönmedi (90 sn). Geri dönüş: runbook Bölüm 7"
fi

# ── 7. Duman testi ───────────────────────────────────────────────────────────
step "7/7  Duman testi"
DOMAIN="$(grep -E '^COGNIVAULT_DOMAIN=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
if ! "$ROOT_DIR/scripts/prod/smoke_test.sh" "https://${DOMAIN}"; then
  echo "" >&2
  echo "Duman testi düştü. Servisler AYAKTA bırakıldı ki inceleyebilesin." >&2
  echo "Geri dönüş adımları: docs/ops/prod-deploy-runbook.md Bölüm 7" >&2
  exit 1
fi

cat <<SUMMARY

============================================================
DAĞITIM TAMAM — https://${DOMAIN}
============================================================
Sonraki adımlar:
  1. Kliniği provizyonla:  docker compose -f docker-compose.prod.yml exec backend \\
       python -m app.onboarding.provision --help
  2. Telefon numarasını bağla (F1):  ... exec backend \\
       python -m app.ops.bind_channel --clinic <slug> --phone "+90..."
  3. İlk yedek provasını doğrula:  ... exec backend python -m app.ops.backup drill
  4. Günlük sağlık kontrolü: runbook Bölüm 6
SUMMARY
