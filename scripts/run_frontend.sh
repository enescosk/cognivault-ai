#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5200}"
VITE_API_URL="${VITE_API_URL:-http://127.0.0.1:8000/api}" \
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort
