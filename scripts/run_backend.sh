#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/backend/.venv/bin/activate"
cd "$ROOT_DIR/backend"
uvicorn app.main:app --reload
