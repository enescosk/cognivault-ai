#!/usr/bin/env bash
# Ses demosu: senaryoyu seçtiğin sesle konuştur, mp3 + görüşme metni üret.
#
#   ./scripts/voice_demo.sh --senaryolar                       # senaryolar
#   ./scripts/voice_demo.sh --sesler                           # hesaptaki sesler
#   ./scripts/voice_demo.sh --senaryo randevu --ses-ara meloxia --oynat
#   ./scripts/voice_demo.sh --senaryo giden-tanisma --model flash --hiz 1.05
#   ./scripts/voice_demo.sh --senaryo randevu --yerel           # Piper ile karşılaştır
#
# Backend ayakta olmalı (./scripts/run_backend.sh). Parola COGNIVAULT_PAROLA
# ortam değişkeninden okunur, yoksa terminalde sorulur.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON="venv/bin/python"
else
  echo "Backend virtualenv bulunamadı. Önce ./scripts/setup_local.sh çalıştır." >&2
  exit 1
fi

exec "$PYTHON" -m app.ops.voice_demo "$@"
