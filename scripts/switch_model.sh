#!/usr/bin/env bash
# Demo lokal LLM modelini değiştir + backend'i yeniden başlat.
# Kullanım:
#   ./scripts/switch_model.sh 7b     # qwen2.5:7b-instruct'a geç (daha iyi Türkçe)
#   ./scripts/switch_model.sh 3b     # qwen2.5:3b-instruct'a geç (güvenli/hızlı)
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

case "${1:-}" in
  3b) MODEL="qwen2.5:3b-instruct" ;;
  7b) MODEL="qwen2.5:7b-instruct" ;;
  *)  echo "Kullanım: $0 [3b|7b]"; exit 1 ;;
esac

# Model yoksa indir
ollama list 2>/dev/null | grep -q "$MODEL" || { echo "İndiriliyor: $MODEL"; ollama pull "$MODEL"; }

# .env içindeki LOCAL_LLM_MODEL satırını güncelle (yoksa ekle)
if grep -q "^LOCAL_LLM_MODEL=" "$ENV_FILE"; then
  sed -i '' "s|^LOCAL_LLM_MODEL=.*|LOCAL_LLM_MODEL=$MODEL|" "$ENV_FILE"
else
  echo "LOCAL_LLM_MODEL=$MODEL" >> "$ENV_FILE"
fi
echo "✓ .env güncellendi → LOCAL_LLM_MODEL=$MODEL"

# Modeli ısıt
curl -s -m 120 http://localhost:11434/v1/chat/completions -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"merhaba\"}],\"max_tokens\":5}" \
  >/dev/null 2>&1 && echo "✓ Model ısındı"

# Backend'i yeniden başlat (yeni .env okunur)
pkill -f "uvicorn app.main" 2>/dev/null; sleep 1
if [[ -d "$ROOT_DIR/backend/venv" ]]; then source "$ROOT_DIR/backend/venv/bin/activate";
elif [[ -d "$ROOT_DIR/backend/.venv" ]]; then source "$ROOT_DIR/backend/.venv/bin/activate"; fi
( cd "$ROOT_DIR/backend" && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 >/tmp/cognivault-backend.log 2>&1 & )
for i in $(seq 1 20); do curl -s -m 2 http://localhost:8000/docs >/dev/null 2>&1 && break; sleep 1; done
echo "✓ Backend yeniden başladı — aktif model: $MODEL"
