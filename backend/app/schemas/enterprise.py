from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.appointment import AppointmentResponse
from app.schemas.chat import ChatMessageResponse


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    description: str | None = None
    is_active: bool


class EnterpriseCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    full_name: str
    email: str | None = None
    phone: str | None = None
    external_ref: str | None = None


class EnterpriseTicketResponse(BaseModel):
    id: int
    session_id: int | None = None
    customer: EnterpriseCustomerResponse
    department: DepartmentResponse | None = None
    intent: str
    description: str
    status: str
    priority: str
    confidence: int
    handoff_package: dict | None = None
    created_at: datetime
    updated_at: datetime


class EnterpriseTicketStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(open|in_progress|escalated|closed)$")
    resolution_note: str | None = None


class EnterpriseSessionSummary(BaseModel):
    id: int
    chat_session_id: int
    customer: EnterpriseCustomerResponse
    department: DepartmentResponse | None = None
    status: str
    intent: str | None = None
    confidence: int
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class EnterpriseSessionDetail(EnterpriseSessionSummary):
    messages: list[ChatMessageResponse]
    handoff_package: dict | None = None


class EnterpriseMetricsResponse(BaseModel):
    organization: OrganizationResponse
    total_tickets: int
    active_sessions: int
    escalations: int
    appointments: int


class EnterpriseOverviewResponse(BaseModel):
    metrics: EnterpriseMetricsResponse
    departments: list[DepartmentResponse]
    tickets: list[EnterpriseTicketResponse]
    sessions: list[EnterpriseSessionSummary]


class EnterpriseSessionCreateRequest(BaseModel):
    customer_name: str = Field(default="Demo Caller", min_length=2)
    customer_email: str | None = None
    customer_phone: str | None = None
    channel: str = "web_chat"


class EnterpriseMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class EnterpriseDecisionResponse(BaseModel):
    intent: str
    department: DepartmentResponse | None = None
    confidence: int
    action: str
    ticket: EnterpriseTicketResponse | None = None
    appointment: AppointmentResponse | None = None
    handoff_package: dict | None = None
    explanation: str


class EnterpriseMessageResponse(BaseModel):
    session: EnterpriseSessionDetail
    assistant_message: str
    decision: EnterpriseDecisionResponse
