#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DB_FILE="${COGNIVAULT_DB_FILE:-$BACKEND_DIR/data/cognivault.db}"

if [[ "$DB_FILE" != *.db ]]; then
  echo "Refusing to reset non-.db path: $DB_FILE" >&2
  exit 1
fi

mkdir -p "$(dirname "$DB_FILE")"
rm -f "$DB_FILE" "$DB_FILE-shm" "$DB_FILE-wal"

if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
elif [[ -x "$BACKEND_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$BACKEND_DIR/venv/bin/python"
else
  echo "Demo database removed. Run ./scripts/setup_local.sh before reseeding." >&2
  exit 0
fi

cd "$BACKEND_DIR"
DATABASE_URL="sqlite:///$DB_FILE" SEED_DEMO_DATA=true "$PYTHON_BIN" - <<'PY'
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.data import seed_database

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    seed_database(db)
finally:
    db.close()
PY

echo "Demo database reset and seeded: $DB_FILE"
