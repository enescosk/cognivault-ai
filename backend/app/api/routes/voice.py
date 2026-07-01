"""Provider-agnostic speech endpoints.

STT and TTS can run with local model engines first (Whisper.cpp / Piper) and
fall back to OpenAI only when configured. The route layer stays stable while
the model backend changes underneath it.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.voice_factory import get_stt_provider, get_tts_provider
from app.api.dependencies import get_current_user, get_db
from app.models import Clinic, User
from app.services.voice_ai_service import synthesize_speech_bytes, transcribe_audio_bytes, voice_capabilities

router = APIRouter(prefix="/voice", tags=["voice"])

TTS_VOICE = "nova"


def _external_transfer_allowed(db: Session, clinic_id: int | None) -> bool:
    """Klinik sınır-ötesi rızasını (`allow_cross_border_processors`) okur.

    `clinic_id` verilmezse ya da klinik bulunamazsa varsayılan KAPALI (fail-closed)
    — bkz. `build_compliance_profile`'daki "external_voice_stt_tts" işlemcisi.
    """
    if clinic_id is None:
        return False
    clinic = db.scalars(select(Clinic).where(Clinic.id == clinic_id)).first()
    if clinic is None:
        return False
    return bool((clinic.settings_json or {}).get("allow_cross_border_processors", False))


# ── Whisper: ses → metin ──────────────────────────────────────────────────────

@router.get("/capabilities")
def get_voice_capabilities(
    current_user: User = Depends(get_current_user),
) -> dict:
    return voice_capabilities()


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile,
    language: str = "tr",
    clinic_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    MediaRecorder webm blob'unu metne çevirir.
    Offline öncelik: Whisper.cpp. Bulut fallback: OpenAI Whisper.
    """
    audio_bytes = await file.read()
    filename = file.filename or "audio.webm"
    transcript, provider = transcribe_audio_bytes(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=file.content_type or "audio/webm",
        language=language,
        external_transfer_allowed=_external_transfer_allowed(db, clinic_id),
    )
    return {"text": transcript, "provider": provider}


# ── OpenAI TTS: metin → ses ───────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = TTS_VOICE        # nova / onyx / shimmer / alloy / echo / fable
    speed: float = 1.0             # 0.25–4.0; 1.0 normal
    is_confirmation: bool = False  # True → use tts-1-hd for higher quality
    clinic_id: int | None = None   # sınır-ötesi rıza kontrolü için (bkz. _external_transfer_allowed)


@router.post("/synthesize")
async def synthesize_speech(
    body: SynthesizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Metni sese çevirir.
    Offline öncelik: Piper. Bulut fallback: OpenAI TTS.
    is_confirmation=true → tts-1-hd (better quality for appointment confirmations).
    """
    result = synthesize_speech_bytes(
        text=body.text, voice=body.voice, speed=body.speed,
        is_confirmation=body.is_confirmation,
        external_transfer_allowed=_external_transfer_allowed(db, body.clinic_id),
    )

    return StreamingResponse(
        io.BytesIO(result.audio),
        media_type=result.media_type,
        headers={
            "Content-Disposition": f"inline; filename={result.filename}",
            "X-Cognivault-Voice-Provider": result.provider,
        },
    )
