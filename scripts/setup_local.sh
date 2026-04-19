#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DB_DIR="$BACKEND_DIR/data"
VENV_DIR="$BACKEND_DIR/.venv"

mkdir -p "$DB_DIR"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

cd "$FRONTEND_DIR"
npm install

cat <<EOF

Local setup is ready.

Backend:
  source "$VENV_DIR/bin/activate"
  cd "$BACKEND_DIR"
  uvicorn app.main:app --reload

Frontend:
  cd "$FRONTEND_DIR"
  npm run dev

Database:
  SQLite local dev database will be created at:
  $DB_DIR/cognivault.db

If you later want Docker/PostgreSQL, docker-compose.yml still forces PostgreSQL inside containers.
EOF
