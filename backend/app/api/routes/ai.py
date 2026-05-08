from __future__ import annotations

from fastapi import APIRouter, Depends

from app.ai.runtime import llm_capabilities
from app.api.dependencies import get_current_user
from app.models import User
from app.services.voice_ai_service import voice_capabilities


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/capabilities")
def get_ai_capabilities(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "llm": llm_capabilities(),
        "voice": voice_capabilities(),
        "architecture": {
            "mode": "provider_agnostic_local_first",
            "contract": "OpenAI-compatible chat completions for local LLMs; Whisper.cpp for STT; Piper for TTS",
            "human_handoff": True,
            "audit_ready": True,
        },
    }
