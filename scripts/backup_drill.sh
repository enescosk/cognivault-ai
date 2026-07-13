#!/usr/bin/env bash
# Yedekleme PROVASI: yedekle → doğrula → geçici hedefe geri yükle → karşılaştır.
# Kanıt backend/data/backups/latest.json'a yazılır; zincir kırıksa çıkış kodu 1.
# "Yedeğimiz var" cümlesi ancak bu script yeşilken kurulabilir.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT_DIR/backend/.venv" ]]; then source "$ROOT_DIR/backend/.venv/bin/activate";
elif [[ -d "$ROOT_DIR/backend/venv" ]]; then source "$ROOT_DIR/backend/venv/bin/activate";
else echo "Backend virtualenv yok. Önce ./scripts/setup_local.sh çalıştırın." >&2; exit 1; fi

cd "$ROOT_DIR/backend"
exec python -m app.ops.backup drill "$@"
