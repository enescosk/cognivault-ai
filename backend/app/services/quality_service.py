from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.runtime import llm_capabilities
from app.models import AuditLog, AuditResultStatus, RoleName, User
from app.services.eval_artifact_service import load_latest_eval_artifact
from app.services.voice_ai_service import voice_capabilities


@dataclass(frozen=True)
class QualityScenario:
    id: str
    name: str
    area: str
    real_world_signal: str
    expected_guardrail: str
    automated: bool = True


SCENARIOS: tuple[QualityScenario, ...] = (
    QualityScenario(
        id="noisy_tr_appointment",
        name="Noisy Turkish appointment booking",
        area="chat",
        real_world_signal="tekink destk, calismio, yarin, phone number in one message",
        expected_guardrail="Detect department/date/phone, keep Turkish, create appointment through backend tools.",
    ),
    QualityScenario(
        id="offline_stream_fallback",
        name="Offline streaming fallback",
        area="chat",
        real_world_signal="No cloud/local LLM provider is configured",
        expected_guardrail="SSE chat still answers through the guided local workflow.",
    ),
    QualityScenario(
        id="enterprise_urgent_escalation",
        name="Enterprise urgent escalation",
        area="enterprise",
        real_world_signal="internet/vpn broken plus human representative request",
        expected_guardrail="Escalate to Technical Support with high-priority ticket and handoff package.",
    ),
    QualityScenario(
        id="local_voice_roundtrip",
        name="Local voice provider roundtrip",
        area="voice",
        real_world_signal="Local STT/TTS binaries are configured",
        expected_guardrail="Transcribe with Whisper.cpp-compatible provider and synthesize with Piper-compatible provider.",
    ),
    QualityScenario(
        id="clinical_emergency_shadow",
        name="Clinical emergency shadow review",
        area="clinical",
        real_world_signal="Chest pain, breathing difficulty, severe symptoms",
        expected_guardrail="Never auto-resolve; create doctor/operator review with emergency guidance.",
    ),
)


def _recent_failure_count(db: Session) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.timestamp >= since,
            AuditLog.result_status == AuditResultStatus.FAILURE,
        )
    ) or 0


def _recent_activity_count(db: Session) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(select(func.count(AuditLog.id)).where(AuditLog.timestamp >= since)) or 0


def _feedback_backlog_count(db: Session) -> int:
    return db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action_type == "quality.feedback_submitted")) or 0


def _recommendations(llm: dict, voice: dict, recent_failures: int) -> list[dict]:
    items: list[dict] = []
    if llm["active_provider"] == "local_rules":
        items.append({
            "priority": "high",
            "area": "llm",
            "title": "Local LLM runtime is not configured",
            "action": "Set LOCAL_LLM_BASE_URL to an OpenAI-compatible local model server before production trials.",
        })
    if not voice["stt"]["offline_capable"]:
        items.append({
            "priority": "medium",
            "area": "voice",
            "title": "Offline STT is not ready",
            "action": "Configure WHISPER_CPP_BINARY and WHISPER_CPP_MODEL for API-free customer voice understanding.",
        })
    if not voice["tts"]["offline_capable"]:
        items.append({
            "priority": "medium",
            "area": "voice",
            "title": "Offline TTS is not ready",
            "action": "Configure PIPER_BINARY and PIPER_VOICE_MODEL for local speech playback.",
        })
    if recent_failures:
        items.append({
            "priority": "high",
            "area": "reliability",
            "title": "Recent backend failures detected",
            "action": "Review audit failures from the last 24 hours and add regression tests for recurring patterns.",
        })
    if load_latest_eval_artifact() is None:
        items.append({
            "priority": "high",
            "area": "evaluation",
            "title": "No latest eval artifact is attached",
            "action": "Publish backend/data/quality/latest_report.json from CI so the quality score reflects real scenario pass rates.",
        })
    if not items:
        items.append({
            "priority": "low",
            "area": "quality",
            "title": "Baseline looks healthy",
            "action": "Add more tenant-specific golden conversations before the next model/provider change.",
        })
    return items


def quality_report(db: Session, current_user: User) -> dict:
    llm = llm_capabilities()
    voice = voice_capabilities()
    recent_failures = _recent_failure_count(db)
    recent_activity = _recent_activity_count(db)
    feedback_backlog = _feedback_backlog_count(db)
    eval_artifact = load_latest_eval_artifact()
    automated_count = sum(1 for scenario in SCENARIOS if scenario.automated)
    provider_score = 0
    provider_score += 30 if llm["active_provider"] != "local_rules" else 18
    provider_score += 20 if voice["stt"]["active_provider"] != "unconfigured" else 8
    provider_score += 20 if voice["tts"]["active_provider"] != "unconfigured" else 8
    provider_score += 20 if recent_failures == 0 else max(0, 20 - min(20, recent_failures * 4))
    provider_score += 10 if automated_count >= 5 else automated_count * 2
    if eval_artifact is not None:
        provider_score += min(20, int(eval_artifact.pass_rate / 5))
    else:
        provider_score -= 15
    score = min(100, provider_score)
    if eval_artifact is None:
        score = min(score, 74)
    elif eval_artifact.pass_rate < 95:
        score = min(score, 89)

    return {
        "score": score,
        "grade": "excellent" if score >= 90 else "strong" if score >= 75 else "needs_work",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "role": current_user.role.name.value,
        "metrics": {
            "automated_scenarios": automated_count,
            "recent_audit_events": recent_activity,
            "recent_failures": recent_failures,
            "offline_chat_ready": True,
            "local_llm_ready": llm["active_provider"] == "local_openai_compatible",
            "local_voice_ready": voice["stt"]["offline_capable"] and voice["tts"]["offline_capable"],
            "eval_pass_rate": eval_artifact.pass_rate if eval_artifact else None,
            "eval_total": eval_artifact.total if eval_artifact else 0,
            "p95_latency_ms": eval_artifact.p95_latency_ms if eval_artifact else None,
            "feedback_backlog": feedback_backlog,
        },
        "latest_eval": eval_artifact.__dict__ if eval_artifact else None,
        "llm": llm,
        "voice": voice,
        "scenarios": [
            {
                "id": scenario.id,
                "name": scenario.name,
                "area": scenario.area,
                "real_world_signal": scenario.real_world_signal,
                "expected_guardrail": scenario.expected_guardrail,
                "automated": scenario.automated,
                "status": "covered" if scenario.automated else "manual",
            }
            for scenario in SCENARIOS
        ],
        "recommendations": _recommendations(llm, voice, recent_failures),
        "can_manage_feedback": current_user.role.name in {RoleName.OPERATOR, RoleName.ADMIN},
    }
