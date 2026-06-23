#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LAN_IP="${COGNIVAULT_LAN_IP:-}"
if [[ -z "$LAN_IP" ]] && command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
fi

if [[ -z "$LAN_IP" ]]; then
  echo "LAN IP bulunamadı. COGNIVAULT_LAN_IP=192.168.x.x ile tekrar çalıştır." >&2
  exit 1
fi

export EXPO_PUBLIC_API_URL="http://${LAN_IP}:8000/api"

echo "Cogni Klinik telefon modu"
echo "API: $EXPO_PUBLIC_API_URL"
echo "Telefon ve bilgisayar aynı Wi-Fi'da olmalı. Expo Go ile QR kodu tara."

cd "$ROOT_DIR/mobile"
exec npm run start -- --lan
