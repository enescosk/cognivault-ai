#!/usr/bin/env bash
# Dağıtılmış bir CogniVault örneğini DIŞARIDAN doğrular — "container ayakta"
# değil, "hasta gerçekten randevu alabilir mi" sorusuna yaklaşır.
#
# Kullanım:
#   ./scripts/prod/smoke_test.sh https://klinik.example.com
#   ./scripts/prod/smoke_test.sh            → .env.prod'daki COGNIVAULT_DOMAIN
#
# Her kontrol tek satır PASS/FAIL basar; biri bile düşerse çıkış kodu 1.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${1:-}"

if [[ -z "$BASE_URL" ]]; then
  if [[ -f "$ROOT_DIR/.env.prod" ]]; then
    DOMAIN="$(grep -E '^COGNIVAULT_DOMAIN=' "$ROOT_DIR/.env.prod" | tail -1 | cut -d= -f2-)"
    [[ -n "${DOMAIN:-}" ]] && BASE_URL="https://${DOMAIN}"
  fi
fi
if [[ -z "$BASE_URL" ]]; then
  echo "Kullanım: $0 <base-url>   (ya da .env.prod içinde COGNIVAULT_DOMAIN tanımlayın)" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"

FAILURES=0
pass() { printf '  PASS  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

# HTTP durum kodunu döndürür (bağlanamazsa 000).
status_of() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$1" 2>/dev/null || echo "000"
}

echo "CogniVault duman testi — $BASE_URL"
echo "------------------------------------------------------------"

# 1) TLS gerçekten kurulmuş mu (sertifika doğrulaması AÇIK; -k YOK).
if curl -sS --max-time 15 -o /dev/null "$BASE_URL/healthz" 2>/dev/null; then
  pass "TLS sertifikası geçerli ve zincir doğrulanıyor"
else
  fail "TLS doğrulanamadı — sertifika alınmamış ya da DNS yanlış olabilir"
fi

# 2) HTTP→HTTPS yönlendirmesi (Caddy otomatik yapar; hasta http yazarsa da gitmeli).
HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://${BASE_URL#https://}/healthz" 2>/dev/null || echo "000")"
if [[ "$HTTP_CODE" == "301" || "$HTTP_CODE" == "302" || "$HTTP_CODE" == "308" ]]; then
  pass "HTTP isteği HTTPS'e yönlendiriliyor ($HTTP_CODE)"
else
  fail "HTTP→HTTPS yönlendirmesi beklenmedik: $HTTP_CODE"
fi

# 3) Canlılık.
[[ "$(status_of "$BASE_URL/healthz")" == "200" ]] \
  && pass "/healthz 200" || fail "/healthz 200 dönmedi"

# 4) Hazırlık — DB erişilemezse 503 döner, bu yüzden 200 gerçek bir kanıttır.
READY_CODE="$(status_of "$BASE_URL/readyz")"
if [[ "$READY_CODE" == "200" ]]; then
  pass "/readyz 200 (veritabanı erişilebilir)"
else
  fail "/readyz $READY_CODE — veritabanı bağlantısı yok (503 = DB ölü)"
fi

# 5) API gerçekten servis ediliyor mu (Caddy /api/* yönlendirmesi doğru mu).
#    Kimliksiz istek 401/403 döner; ÖNEMLİ olan 404/502 DÖNMEMESİ.
API_CODE="$(status_of "$BASE_URL/api/agents/decisions")"
if [[ "$API_CODE" == "401" || "$API_CODE" == "403" ]]; then
  pass "/api/* backend'e yönleniyor ve kimlik doğrulaması istiyor ($API_CODE)"
elif [[ "$API_CODE" == "200" ]]; then
  fail "/api/agents/decisions kimliksiz 200 döndü — yetkilendirme AÇIK DEĞİL"
else
  fail "/api/* yönlendirmesi bozuk: $API_CODE (404=Caddy kuralı, 502=backend ölü)"
fi

# 6) Metrikler dışarı kapalı olmalı (istek hacmi/klinik kimliği sızdırır).
METRICS_CODE="$(status_of "$BASE_URL/metrics")"
if [[ "$METRICS_CODE" == "404" || "$METRICS_CODE" == "403" ]]; then
  pass "/metrics dışarıya kapalı ($METRICS_CODE)"
else
  fail "/metrics dışarıdan erişilebilir ($METRICS_CODE) — iç ağa kapatın"
fi

# 7) SPA yükleniyor mu (frontend konteyneri ve Caddy fallback'i).
if curl -sS --max-time 15 "$BASE_URL/" 2>/dev/null | grep -qi '<div id="root"'; then
  pass "Web arayüzü servis ediliyor"
else
  fail "Web arayüzü yüklenmedi — frontend konteynerini kontrol edin"
fi

# 8) Güvenlik başlıkları (SecurityHeadersMiddleware).
HEADERS="$(curl -sS -I --max-time 15 "$BASE_URL/healthz" 2>/dev/null || true)"
if grep -qi 'strict-transport-security' <<<"$HEADERS"; then
  pass "HSTS başlığı mevcut"
else
  fail "HSTS başlığı yok"
fi

echo "------------------------------------------------------------"
if [[ "$FAILURES" -eq 0 ]]; then
  echo "SONUÇ: TÜM KONTROLLER GEÇTİ"
  exit 0
fi
echo "SONUÇ: $FAILURES kontrol BAŞARISIZ — runbook'taki geri dönüş adımına bakın"
exit 1
