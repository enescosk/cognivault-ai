"""
Ses servisleri — Whisper (STT) + OpenAI TTS (metin→ses).

STT akışı:
  Tarayıcı MediaRecorder → webm blob → POST /transcribe → Whisper → metin

TTS akışı:
  AI mesaj metni → POST /synthesize → OpenAI TTS (nova sesi) → mp3 stream
  Tarayıcıda Web Audio API ile çalınır — tarayıcı sentezinden çok daha doğal.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/voice", tags=["voice"])
settings = get_settings()

# OpenAI TTS sesi — Türkçe için en doğal sonucu veren:
# nova  → genç, sıcak, akıcı kadın sesi
# onyx  → derin, sakin erkek sesi
# shimmer → enerjik, net kadın sesi
TTS_VOICE = "nova"
TTS_MODEL = "tts-1"   # tts-1-hd daha yüksek kalite ama 2× maliyetli


# ── Whisper: ses → metin ──────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile,
    language: str = "tr",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    MediaRecorder webm blob'unu OpenAI Whisper-1 ile metne çevirir.
    language: "tr" (varsayılan) veya "en" — açıkça vermek doğruluğu artırır.
    """
    if not settings.openai_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="OpenAI API key gerekli.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ses dosyası boş.")

    filename = file.filename or "audio.webm"
    client = OpenAI(api_key=settings.openai_api_key)

    try:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, io.BytesIO(audio_bytes), file.content_type or "audio/webm"),
            language=language,
            response_format="text",
        )
        transcript = result.strip() if isinstance(result, str) else str(result).strip()
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail=f"Ses tanıma hatası: {exc}") from exc

    return {"text": transcript}


# ── OpenAI TTS: metin → ses ───────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = TTS_VOICE   # nova / onyx / shimmer / alloy / echo / fable
    speed: float = 1.0        # 0.25–4.0; 1.0 normal


@router.post("/synthesize")
async def synthesize_speech(
    body: SynthesizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Metni OpenAI TTS ile mp3 sesine çevirir.
    Tarayıcı doğrudan mp3 stream'i alır ve Audio API ile çalar.

    Neden Web Speech Synthesis değil?
    - Web Speech: her tarayıcı/OS'ta farklı, çoğunda robotik, Türkçe sesi yetersiz.
    - OpenAI TTS: gerçek sinir ağı sesi, Türkçe'yi iyi telaffuz eder, her platformda aynı.
    """
    if not settings.openai_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="OpenAI API key gerekli.")

    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Metin boş.")

    # 4096 karakter limiti — uzun metinleri kırp
    text = text[:4096]

    client = OpenAI(api_key=settings.openai_api_key)

    try:
        # stream=True ile byte'ları akış olarak al → belleği verimli kullan
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=body.voice,       # type: ignore[arg-type]
            input=text,
            response_format="mp3",
            speed=max(0.25, min(4.0, body.speed)),
        )
        audio_bytes = response.content   # tüm mp3 bytes
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail=f"Ses sentezi hatası: {exc}") from exc

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"},
    )
