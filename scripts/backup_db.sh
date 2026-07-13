#!/usr/bin/env bash
# Veritabanı yedeği alır (SQLite: online backup API; PostgreSQL: pg_dump -Fc).
# Kullanım: ./scripts/backup_db.sh            → .env'deki DATABASE_URL yedeklenir
#          ./scripts/backup_db.sh --database-url sqlite:///data/x.db
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT_DIR/backend/.venv" ]]; then source "$ROOT_DIR/backend/.venv/bin/activate";
elif [[ -d "$ROOT_DIR/backend/venv" ]]; then source "$ROOT_DIR/backend/venv/bin/activate";
else echo "Backend virtualenv yok. Önce ./scripts/setup_local.sh çalıştırın." >&2; exit 1; fi

cd "$ROOT_DIR/backend"
exec python -m app.ops.backup backup "$@"
