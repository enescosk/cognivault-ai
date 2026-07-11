from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Clinic,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicIntent,
    ClinicMessage,
    ClinicMessageSender,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    ClinicalVoiceQARun,
)


@dataclass(frozen=True)
class PilotMetric:
    id: str
    label: str
    value: float
    target: float | None
    unit: str
    passed: bool | None


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def build_pilot_metrics(db: Session, clinic: Clinic, *, days: int = 7) -> dict:
    """Pilot-readiness KPIs from real conversation, appointment and voice metadata.

    This is intentionally conservative: missing telemetry counts against the
    denominator instead of being ignored, so pilot readiness cannot look better
    than the data quality actually supports.
    """
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    conversations = db.scalars(
        select(ClinicConversation).where(
            ClinicConversation.clinic_id == clinic.id,
            ClinicConversation.created_at >= since,
        )
    ).all()
    conversation_ids = [c.id for c in conversations]
    total_conversations = len(conversations)

    appointments = db.scalars(
        select(ClinicalAppointment).where(
            ClinicalAppointment.clinic_id == clinic.id,
            ClinicalAppointment.created_at >= since,
        )
    ).all()
    successful_appointments = [
        a
        for a in appointments
        if a.status in {ClinicalAppointmentStatus.PENDING, ClinicalAppointmentStatus.CONFIRMED}
    ]
    successful_conversation_ids = {
        a.conversation_id for a in successful_appointments if a.conversation_id is not None
    }

    under_60 = 0
    for appointment in successful_appointments:
        if appointment.conversation_id is None:
            continue
        conversation = next((c for c in conversations if c.id == appointment.conversation_id), None)
        elapsed = _seconds_between(conversation.created_at if conversation else None, appointment.created_at)
        if elapsed is not None and elapsed <= 60:
            under_60 += 1

    messages: list[ClinicMessage] = []
    if conversation_ids:
        messages = db.scalars(
            select(ClinicMessage).where(ClinicMessage.conversation_id.in_(conversation_ids))
        ).all()

    voice_messages = [
        m
        for m in messages
        if m.sender == ClinicMessageSender.PATIENT
        and isinstance((m.metadata_json or {}).get("voice_transcript"), dict)
    ]
    voice_conversation_ids = {m.conversation_id for m in voice_messages}
    voice_event_counters: list[dict] = [
        c.metadata_json.get("voice_event_counters")
        for c in conversations
        if isinstance((c.metadata_json or {}).get("voice_event_counters"), dict)
    ]
    no_result_events = sum(int(c.get("no_result", 0) or 0) for c in voice_event_counters)
    stt_failure_events = sum(int(c.get("stt_failure", 0) or 0) for c in voice_event_counters)
    retry_prompt_events = sum(int(c.get("retry_prompt", 0) or 0) for c in voice_event_counters)
    voice_attempts = len(voice_messages) + no_result_events + stt_failure_events
    voice_confidences = [
        float(meta["confidence"])
        for m in voice_messages
        if isinstance((meta := (m.metadata_json or {}).get("voice_transcript")), dict)
        and isinstance(meta.get("confidence"), (int, float))
    ]
    avg_voice_confidence = (
        round((sum(voice_confidences) / len(voice_confidences)) * 100.0, 2)
        if voice_confidences
        else 0.0
    )
    low_voice_confidence_messages = sum(1 for value in voice_confidences if value < 0.7)

    operator_conversation_ids = {
        m.conversation_id for m in messages if m.sender == ClinicMessageSender.OPERATOR
    }
    operator_conversation_ids.update(
        c.id for c in conversations if c.status == ClinicConversationStatus.WAITING_HUMAN
    )

    emergency_conversations = [c for c in conversations if c.intent == ClinicIntent.MEDICAL_EMERGENCY]
    emergency_routed = 0
    for conversation in emergency_conversations:
        routed = False
        for message in messages:
            if message.conversation_id != conversation.id:
                continue
            meta = message.metadata_json or {}
            if meta.get("emergency_routed") is True:
                routed = True
            if message.sender != ClinicMessageSender.PATIENT and "112" in (message.content or ""):
                routed = True
        if routed:
            emergency_routed += 1
    emergency_safety_incidents = max(0, len(emergency_conversations) - emergency_routed)

    voice_qa_runs = db.scalars(
        select(ClinicalVoiceQARun).where(
            ClinicalVoiceQARun.clinic_id == clinic.id,
            ClinicalVoiceQARun.created_at >= since,
        )
    ).all()
    voice_qa_blocking = sum(1 for run in voice_qa_runs if run.severity == "blocking")
    voice_qa_major = sum(1 for run in voice_qa_runs if run.severity == "major")

    booking_success_rate = _pct(len(successful_conversation_ids), total_conversations)
    under_60_rate = _pct(under_60, len(successful_conversation_ids))
    voice_coverage_rate = _pct(len(voice_conversation_ids), total_conversations)
    no_result_rate = _pct(no_result_events, voice_attempts)
    retry_prompt_rate = _pct(retry_prompt_events, voice_attempts)
    operator_intervention_rate = _pct(len(operator_conversation_ids), total_conversations)

    metrics = [
        PilotMetric(
            id="booking_success_rate",
            label="Booking success",
            value=booking_success_rate,
            target=70.0,
            unit="percent",
            passed=booking_success_rate >= 70.0 if total_conversations else None,
        ),
        PilotMetric(
            id="under_60_second_booking_rate",
            label="Under 60 seconds",
            value=under_60_rate,
            target=50.0,
            unit="percent",
            passed=under_60_rate >= 50.0 if successful_conversation_ids else None,
        ),
        PilotMetric(
            id="voice_transcript_coverage",
            label="Voice transcript coverage",
            value=voice_coverage_rate,
            target=90.0,
            unit="percent",
            passed=voice_coverage_rate >= 90.0 if total_conversations else None,
        ),
        PilotMetric(
            id="voice_stt_confidence",
            label="Voice STT confidence",
            value=avg_voice_confidence,
            target=80.0,
            unit="percent",
            passed=avg_voice_confidence >= 80.0 if voice_confidences else None,
        ),
        PilotMetric(
            id="voice_no_result_rate",
            label="Voice no-result rate",
            value=no_result_rate,
            target=15.0,
            unit="percent",
            passed=no_result_rate <= 15.0 if voice_attempts else None,
        ),
        PilotMetric(
            id="voice_retry_prompt_rate",
            label="Voice retry prompt rate",
            value=retry_prompt_rate,
            target=20.0,
            unit="percent",
            passed=retry_prompt_rate <= 20.0 if voice_attempts else None,
        ),
        PilotMetric(
            id="voice_stt_failures",
            label="Voice STT failures",
            value=float(stt_failure_events),
            target=0.0,
            unit="count",
            passed=stt_failure_events == 0,
        ),
        PilotMetric(
            id="operator_intervention_rate",
            label="Operator intervention",
            value=operator_intervention_rate,
            target=25.0,
            unit="percent",
            passed=operator_intervention_rate <= 25.0 if total_conversations else None,
        ),
        PilotMetric(
            id="emergency_safety_incidents",
            label="Emergency safety incidents",
            value=float(emergency_safety_incidents),
            target=0.0,
            unit="count",
            passed=emergency_safety_incidents == 0,
        ),
        PilotMetric(
            id="real_device_qa_runs",
            label="Real-device QA runs",
            value=float(len(voice_qa_runs)),
            target=12.0,
            unit="count",
            passed=len(voice_qa_runs) >= 12 and voice_qa_blocking == 0 and voice_qa_major == 0,
        ),
    ]

    return {
        "window_days": days,
        "totals": {
            "conversations": total_conversations,
            "appointments": len(appointments),
            "successful_appointments": len(successful_appointments),
            "voice_messages": len(voice_messages),
            "voice_attempts": voice_attempts,
            "voice_no_result_events": no_result_events,
            "voice_retry_prompt_events": retry_prompt_events,
            "voice_stt_failure_events": stt_failure_events,
            "voice_confidence_samples": len(voice_confidences),
            "low_voice_confidence_messages": low_voice_confidence_messages,
            "voice_qa_runs": len(voice_qa_runs),
            "voice_qa_blocking_failures": voice_qa_blocking,
            "voice_qa_major_failures": voice_qa_major,
            "operator_interventions": len(operator_conversation_ids),
            "emergency_conversations": len(emergency_conversations),
        },
        "metrics": [metric.__dict__ for metric in metrics],
        "ready_for_pilot": all(metric.passed is not False for metric in metrics),
    }


def build_pilot_weekly_report(db: Session, clinic: Clinic, *, days: int = 7) -> dict:
    days = max(1, min(days, 90))
    report = build_pilot_metrics(db, clinic, days=days)
    metric_lines = []
    for item in report["metrics"]:
        value = _format_metric_value(item["value"], item["unit"])
        target = _format_metric_value(item["target"], item["unit"]) if item["target"] is not None else "-"
        status = "PASS" if item["passed"] is True else "RISK" if item["passed"] is False else "NO DATA"
        metric_lines.append(f"- {item['label']}: {value} / hedef {target} [{status}]")

    totals = report["totals"]
    generated_at = datetime.now(timezone.utc)
    markdown = "\n".join(
        [
            f"# {clinic.name} Pilot Weekly Report",
            "",
            f"Window: last {days} days",
            f"Generated: {generated_at.isoformat()}",
            f"Pilot readiness: {'READY' if report['ready_for_pilot'] else 'RISK'}",
            "",
            "## Totals",
            f"- Conversations: {totals.get('conversations', 0)}",
            f"- Successful appointments: {totals.get('successful_appointments', 0)}",
            f"- Voice attempts: {totals.get('voice_attempts', 0)}",
            f"- Voice messages: {totals.get('voice_messages', 0)}",
            f"- No-result events: {totals.get('voice_no_result_events', 0)}",
            f"- STT failures: {totals.get('voice_stt_failure_events', 0)}",
            f"- Operator interventions: {totals.get('operator_interventions', 0)}",
            f"- Real-device QA runs: {totals.get('voice_qa_runs', 0)}",
            "",
            "## KPIs",
            *metric_lines,
            "",
            "## Next Actions",
            *(_pilot_next_actions(report)),
        ]
    )
    return {
        "window_days": days,
        "generated_at": generated_at,
        "summary": {
            "clinic_name": clinic.name,
            "ready_for_pilot": report["ready_for_pilot"],
            "totals": totals,
        },
        "markdown": markdown,
    }


def build_pilot_launch_checklist(db: Session, clinic: Clinic, *, days: int = 7) -> dict:
    days = max(1, min(days, 90))
    metrics_report = build_pilot_metrics(db, clinic, days=days)
    metric_by_id = {item["id"]: item for item in metrics_report["metrics"]}

    checklist = [
        _check_item(
            "booking_success",
            "Booking success >= 70%",
            metric_by_id.get("booking_success_rate"),
        ),
        _check_item(
            "under_60_seconds",
            "Under-60-second booking >= 50%",
            metric_by_id.get("under_60_second_booking_rate"),
        ),
        _check_item(
            "voice_retry_rate",
            "Voice retry/no-result rates within target",
            metric_by_id.get("voice_retry_prompt_rate"),
            also=metric_by_id.get("voice_no_result_rate"),
        ),
        _check_item(
            "emergency_safety",
            "Emergency safety incidents = 0",
            metric_by_id.get("emergency_safety_incidents"),
        ),
        _check_item(
            "real_device_qa",
            "12 real-device QA runs completed",
            metric_by_id.get("real_device_qa_runs"),
        ),
        {
            "id": "rollback_owner",
            "label": "Rollback owner assigned",
            "status": "manual",
            "detail": "Assign clinic owner + engineering owner before launch.",
        },
        {
            "id": "staff_onboarding",
            "label": "Staff onboarding script rehearsed",
            "status": "manual",
            "detail": "Reception/operator should complete one test booking unaided.",
        },
    ]
    blocking = [item for item in checklist if item["status"] == "risk"]
    return {
        "window_days": days,
        "ready_for_launch": len(blocking) == 0 and metrics_report["ready_for_pilot"],
        "checklist": checklist,
        "rollback_plan": [
            "Switch clinic voice settings to local providers.",
            "Disable patient-page traffic source or route patients to phone/WhatsApp fallback.",
            "Set auto-reply threshold high enough to force human review.",
            "Export/copy weekly report and attach incident notes.",
        ],
        "incident_response": [
            "Severity 1: emergency routing failure, wrong appointment confirmation, or external transfer without consent.",
            "Stop pilot traffic, preserve conversation transcript/voice metadata, assign owner within 15 minutes.",
            "Severity 2: repeated no-result/STT failure above target or operator intervention spike.",
            "Keep pilot limited, review device QA/runbook, update provider/settings before expanding.",
        ],
    }


def _check_item(
    item_id: str,
    label: str,
    metric: dict | None,
    *,
    also: dict | None = None,
) -> dict:
    if metric is None or metric.get("passed") is None:
        return {"id": item_id, "label": label, "status": "no_data", "detail": "No data yet."}
    passed = metric.get("passed") is True and (also is None or also.get("passed") is True)
    detail = f"{metric['label']}={_format_metric_value(metric['value'], metric['unit'])}"
    if also is not None:
        detail += f", {also['label']}={_format_metric_value(also['value'], also['unit'])}"
    return {"id": item_id, "label": label, "status": "pass" if passed else "risk", "detail": detail}


def _format_metric_value(value: float | None, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "percent":
        return f"{round(value)}%"
    if unit == "count":
        return str(round(value))
    return str(value)


def _pilot_next_actions(report: dict) -> list[str]:
    risks = [item for item in report["metrics"] if item["passed"] is False]
    if not risks:
        return ["- Keep monitoring daily and run scheduled real-device QA before expanding traffic."]
    actions = []
    for item in risks:
        if item["id"] == "booking_success_rate":
            actions.append("- Improve guided booking flow and inspect drop-off conversations.")
        elif item["id"] == "under_60_second_booking_rate":
            actions.append("- Reduce voice/slot latency and shorten assistant prompts.")
        elif item["id"] in {"voice_no_result_rate", "voice_retry_prompt_rate", "voice_stt_failures"}:
            actions.append("- Review microphone QA runs, STT provider diagnostics, and noisy-room recordings.")
        elif item["id"] == "operator_intervention_rate":
            actions.append("- Tune auto-reply thresholds and shadow-review routing.")
        elif item["id"] == "real_device_qa_runs":
            actions.append("- Complete at least 12 real-device QA runs with no blocking/major failures.")
        elif item["id"] == "emergency_safety_incidents":
            actions.append("- Block pilot expansion until emergency routing evidence is clean.")
    return list(dict.fromkeys(actions))
