from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.runtime import llm_capabilities
from app.core.config import get_settings
from app.services.voice_ai_service import voice_capabilities


def readiness_report(db: Session) -> dict:
    settings = get_settings()
    checks: dict[str, dict] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "fail", "detail": str(exc)}

    weak_secret = settings.jwt_secret in {"change-me-in-production", "replace-me", "secret"} or len(settings.jwt_secret) < 24
    checks["security"] = {
        "status": "warn" if weak_secret else "ok",
        "jwt_secret_strong": not weak_secret,
        "cors_origins": settings.cors_origin_list,
    }

    llm = llm_capabilities()
    voice = voice_capabilities()
    checks["llm"] = {
        "status": "ok" if llm["offline_capable"] else "warn",
        "active_provider": llm["active_provider"],
        "active_model": llm["active_model"],
        "tool_calling": llm["tool_calling"],
    }
    checks["voice"] = {
        "status": "ok" if voice["stt"]["active_provider"] != "unconfigured" and voice["tts"]["active_provider"] != "unconfigured" else "warn",
        "stt_provider": voice["stt"]["active_provider"],
        "tts_provider": voice["tts"]["active_provider"],
        "offline_capable": voice["stt"]["offline_capable"] and voice["tts"]["offline_capable"],
    }

    from app.services.sms_service import sms_capabilities

    sms = sms_capabilities()
    checks["sms"] = {
        # mock bilinçli demo modu (warn); netgsm seçilip kimlik eksikse
        # hasta mesaj alamıyor demektir — bu bir konfigürasyon hatasıdır (fail).
        "status": "fail" if sms["misconfigured"] else ("ok" if sms["real_delivery"] else "warn"),
        **sms,
    }

    hard_fail = any(check["status"] == "fail" for check in checks.values())
    return {
        "status": "fail" if hard_fail else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app": settings.app_name,
        "checks": checks,
    }
