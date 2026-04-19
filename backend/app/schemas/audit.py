from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    user_id: int | None = None
    session_id: int | None = None
    action_type: str
    tool_name: str | None = None
    result_status: str
    success: bool
    explanation: str
    details: dict | None = None


class MetricsResponse(BaseModel):
    active_sessions: int
    confirmed_appointments: int
    audit_events_today: int
    completion_rate: float
