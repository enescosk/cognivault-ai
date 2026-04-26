from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Appointment, AuditLog, AuditResultStatus, ChatSession, RoleName, User


def log_action(
    db: Session,
    *,
    user_id: int | None,
    action_type: str,
    explanation: str,
    session_id: int | None = None,
    tool_name: str | None = None,
    result_status: AuditResultStatus = AuditResultStatus.INFO,
    success: bool = True,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        session_id=session_id,
        action_type=action_type,
        tool_name=tool_name,
        result_status=result_status,
        success=success,
        explanation=explanation,
        details=details or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_audit_logs(
    db: Session,
    current_user: User,
    limit: int = 100,
    *,
    action_type: str | None = None,
    result_status: str | None = None,
    success: bool | None = None,
    user_id: int | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if current_user.role.name == RoleName.CUSTOMER:
        query = query.where(AuditLog.user_id == current_user.id)
    elif user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action_type:
        query = query.where(AuditLog.action_type.ilike(f"%{action_type.strip()}%"))
    if result_status:
        query = query.where(AuditLog.result_status == AuditResultStatus(result_status))
    if success is not None:
        query = query.where(AuditLog.success.is_(success))
    if from_ts is not None:
        query = query.where(AuditLog.timestamp >= from_ts)
    if to_ts is not None:
        query = query.where(AuditLog.timestamp <= to_ts)
    return list(db.scalars(query))


def get_metrics(db: Session, current_user: "User | None" = None) -> dict:
    today = datetime.now(timezone.utc).date()
    is_customer = current_user is not None and current_user.role.name == RoleName.CUSTOMER

    if is_customer:
        uid = current_user.id  # type: ignore[union-attr]
        active_sessions = (
            db.scalar(
                select(func.count(ChatSession.id)).where(
                    ChatSession.status == "active", ChatSession.user_id == uid
                )
            )
            or 0
        )
        confirmed_appointments = (
            db.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.user_id == uid,
                    Appointment.status == "confirmed",
                )
            )
            or 0
        )
        audit_events_today = (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    func.date(AuditLog.timestamp) == today,
                    AuditLog.user_id == uid,
                )
            )
            or 0
        )
        tool_success = (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.tool_name.is_not(None),
                    AuditLog.success.is_(True),
                    AuditLog.user_id == uid,
                )
            )
            or 0
        )
        tool_total = (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.tool_name.is_not(None), AuditLog.user_id == uid
                )
            )
            or 0
        )
    else:
        active_sessions = db.scalar(select(func.count(ChatSession.id)).where(ChatSession.status == "active")) or 0
        confirmed_appointments = db.scalar(select(func.count(Appointment.id))) or 0
        audit_events_today = (
            db.scalar(select(func.count(AuditLog.id)).where(func.date(AuditLog.timestamp) == today)) or 0
        )
        tool_success = (
            db.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.tool_name.is_not(None), AuditLog.success.is_(True))
            )
            or 0
        )
        tool_total = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.tool_name.is_not(None))) or 0

    completion_rate = round((tool_success / tool_total) * 100, 1) if tool_total else 100.0
    return {
        "active_sessions": active_sessions,
        "confirmed_appointments": confirmed_appointments,
        "audit_events_today": audit_events_today,
        "completion_rate": completion_rate,
    }
