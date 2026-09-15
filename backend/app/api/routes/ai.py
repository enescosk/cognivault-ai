from __future__ import annotations

from fastapi import APIRouter, Depends

from app.ai.runtime import llm_capabilities
from app.api.dependencies import get_current_user
from app.models import User
from app.services.voice_ai_service import voice_capabilities


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/capabilities")
def get_ai_capabilities(current_user: User = Depends(get_current_user)) -> dict:
    from app.services.sms_service import sms_capabilities
    from app.core.config import get_settings
    settings = get_settings()

    return {
        "llm": llm_capabilities(),
        "voice": voice_capabilities(),
        "sms": sms_capabilities(),
        "clinical_llm": {
            "preferred_provider": settings.clinical_llm_provider,
            "astra_model": settings.clinical_astra_model,
            "astra_configured": bool(settings.openai_api_key),
            "external_enabled": settings.clinical_external_ai_allowed,
            "patient_consent_required": True,
            "clinic_permission_required": True,
            "greetings": "local_contextual",
            "history_turn_limit": 6,
            "draft_only": True,
        },
        "architecture": {
            "mode": "provider_agnostic_local_first",
            "contract": "OpenAI-compatible chat completions for local LLMs; Whisper.cpp for STT; Piper for TTS",
            "human_handoff": True,
            "audit_ready": True,
        },
    }
