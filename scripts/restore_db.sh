#!/usr/bin/env bash
# Yedeği hedefe geri yükler (SQLite). Hedef mevcutsa --force ister ve önce
# hedefin .pre-restore-<ts> güvenlik kopyasını alır; bozuk yedek asla yazılmaz.
# Kullanım: ./scripts/restore_db.sh <yedek.db> --target backend/data/cognivault.db [--force]
# NOT: Geri yükleme öncesi backend'i durdurun (uvicorn açık dosyayı tutar).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT_DIR/backend/.venv" ]]; then source "$ROOT_DIR/backend/.venv/bin/activate";
elif [[ -d "$ROOT_DIR/backend/venv" ]]; then source "$ROOT_DIR/backend/venv/bin/activate";
else echo "Backend virtualenv yok. Önce ./scripts/setup_local.sh çalıştırın." >&2; exit 1; fi

cd "$ROOT_DIR/backend"
exec python -m app.ops.backup restore "$@"
