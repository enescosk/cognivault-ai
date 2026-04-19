from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.schemas.audit import AuditLogResponse, MetricsResponse
from app.services.audit_service import get_metrics, list_audit_logs


router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditLogResponse]:
    logs = list_audit_logs(db, current_user, limit)
    return [
        AuditLogResponse(
            id=entry.id,
            timestamp=entry.timestamp,
            user_id=entry.user_id,
            session_id=entry.session_id,
            action_type=entry.action_type,
            tool_name=entry.tool_name,
            result_status=entry.result_status.value,
            success=entry.success,
            explanation=entry.explanation,
            details=entry.details,
        )
        for entry in logs
    ]


@router.get("/metrics", response_model=MetricsResponse)
def get_dashboard_metrics(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> MetricsResponse:
    _ = current_user
    return MetricsResponse(**get_metrics(db))
