#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT_DIR/backend/.venv" ]]; then
  source "$ROOT_DIR/backend/.venv/bin/activate"
elif [[ -d "$ROOT_DIR/backend/venv" ]]; then
  source "$ROOT_DIR/backend/venv/bin/activate"
else
  echo "Backend virtualenv not found. Run ./scripts/setup_local.sh first." >&2
  exit 1
fi
cd "$ROOT_DIR/backend"
uvicorn app.main:app --reload
