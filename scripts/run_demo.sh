#!/usr/bin/env bash
# CogniVault demo başlatıcı — lokal LLM + backend + frontend tek komutla.
# Kullanım:  ./scripts/run_demo.sh
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="qwen2.5:3b-instruct"

echo "▶ 1/4  Ollama (lokal LLM) kontrol ediliyor…"
if ! curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "   Ollama ayakta değil — başlatılıyor (Ollama.app)…"
  open -a Ollama 2>/dev/null || ollama serve >/tmp/ollama-serve.log 2>&1 &
  for i in $(seq 1 15); do
    curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi
curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 \
  && echo "   ✓ Ollama hazır" || { echo "   ✗ Ollama başlatılamadı"; }

echo "▶ 2/4  Model ($MODEL) kontrol ediliyor…"
if ! ollama list 2>/dev/null | grep -qi "qwen2.5:3b"; then
  echo "   Model yok — indiriliyor…"; ollama pull "$MODEL"
fi
# Modeli önceden ısıt (ilk demo cevabı hızlı olsun)
curl -s -m 60 http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"merhaba\"}],\"max_tokens\":5}" \
  >/dev/null 2>&1 && echo "   ✓ Model yüklü ve ısındı"

# Lokal Türkçe TTS sesi (Piper) — yoksa indir (~63MB). Yoksa macOS 'say'e düşer.
# Varsayılan ses: fahrettin (dfki'den belirgin daha doğal prosodi).
PIPER_DIR="$ROOT_DIR/backend/data/piper"
if [[ ! -f "$PIPER_DIR/tr_TR-fahrettin-medium.onnx" ]]; then
  echo "   Lokal TTS sesi indiriliyor (Piper tr_TR fahrettin, ~63MB)…"
  mkdir -p "$PIPER_DIR"
  PV="https://huggingface.co/speaches-ai/piper-tr_TR-fahrettin-medium/resolve/main"
  curl -sL -o "$PIPER_DIR/tr_TR-fahrettin-medium.onnx" "$PV/model.onnx"
  curl -sL -o "$PIPER_DIR/tr_TR-fahrettin-medium.onnx.json" "$PV/config.json"
fi

echo "▶ 3/4  Backend başlatılıyor (http://localhost:8000)…"
pkill -f "uvicorn app.main" 2>/dev/null; sleep 1
# run_backend.sh ile AYNI sıra (.venv → venv): iki script farklı venv seçerse
# ses bağımlılıkları girişe göre değişir ve TTS sessizce robotik say'e düşer.
if [[ -d "$ROOT_DIR/backend/.venv" ]]; then source "$ROOT_DIR/backend/.venv/bin/activate";
elif [[ -d "$ROOT_DIR/backend/venv" ]]; then source "$ROOT_DIR/backend/venv/bin/activate"; fi
( cd "$ROOT_DIR/backend" && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 >/tmp/cognivault-backend.log 2>&1 & )
for i in $(seq 1 20); do
  curl -s -m 2 http://localhost:8000/docs >/dev/null 2>&1 && break; sleep 1
done
echo "   ✓ Backend hazır (log: /tmp/cognivault-backend.log)"

echo "▶ 4/4  Frontend başlatılıyor (http://localhost:5173)…"
pkill -f "vite" 2>/dev/null; sleep 1
( cd "$ROOT_DIR/frontend" && nohup npm run dev >/tmp/cognivault-frontend.log 2>&1 & )
sleep 5
echo "   ✓ Frontend hazır (log: /tmp/cognivault-frontend.log)"

echo
echo "════════════════════════════════════════════════════"
echo "  DEMO HAZIR"
echo "  Uygulama : http://localhost:5173"
echo "  Operatör : operator@cognivault.com / demo123"
echo "  Admin    : admin@cognivault.com    / demo123"
echo "  Klinik   : demo-klinik"
echo "  Lokal LLM: $MODEL (Ollama, %100 yurt içi)"
echo "════════════════════════════════════════════════════"
