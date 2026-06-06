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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.voice_factory import get_stt_provider, get_tts_provider
from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.models import ConsentRecord, ConsentType, User

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
    clinic_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    MediaRecorder webm blob'unu OpenAI Whisper-1 ile metne çevirir.
    language: "tr" (varsayılan) veya "en" — açıkça vermek doğruluğu artırır.

    KVKK Md. 6: `clinic_id` verilirse (klinik modu), o klinik için aktif bir
    `voice_recording` rızası aranır. Yoksa 403 döner.

    Ses, varsayılan olarak lokal faster-whisper ile yurt içinde çözülür; OpenAI
    yalnızca `voice_stt_provider=openai` + `voice_external_enabled` ile devreye girer.
    """
    # KVKK Md. 6 — Klinik bağlamında ses kaydı için hasta açık rızası şart.
    if clinic_id is not None:
        consent_row = db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.clinic_id == clinic_id,
                ConsentRecord.consent_type == ConsentType.VOICE_RECORDING,
                ConsentRecord.granted == True,  # noqa: E712
                ConsentRecord.withdrawn_at.is_(None),
            )
            .order_by(ConsentRecord.granted_at.desc())
            .limit(1)
        ).first()
        if consent_row is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Ses kaydı için hasta açık rızası alınmadan harici transkripsiyon servisi kullanılamaz (KVKK Md. 6).",
            )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ses dosyası boş.")

    try:
        transcript = get_stt_provider().transcribe(audio_bytes, language=language)
    except Exception as exc:  # noqa: BLE001
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
    Metni sese çevirir — varsayılan lokal Piper (tr_TR, nöral); ses yurt içinde
    üretilir. OpenAI yalnızca voice_tts_provider=openai + voice_external_enabled
    ile devreye girer. WAV (lokal) veya MP3 (OpenAI) döner; tarayıcı her ikisini
    de Audio API ile çalar.
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Metin boş.")

    try:
        audio_bytes, mime = get_tts_provider().synthesize(text[:4096], voice=body.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail=f"Ses sentezi hatası: {exc}") from exc

    ext = "wav" if mime == "audio/wav" else "mp3"
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=mime,
        headers={"Content-Disposition": f"inline; filename=speech.{ext}"},
    )
