from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClinicalPatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    full_name: str | None = None
    phone: str
    language: str
    source: str
    created_at: datetime
    updated_at: datetime


class ClinicalMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender: str
    content: str
    language: str
    intent: str | None = None
    confidence_score: float | None = None
    external_message_id: str | None = None
    metadata_json: dict | None = None
    created_at: datetime


class ClinicalConversationSummary(BaseModel):
    id: int
    clinic_id: int
    patient: ClinicalPatientResponse
    channel: str
    status: str
    language: str
    intent: str | None = None
    confidence_score: float | None = None
    persona_name: str | None = None
    doctor_inbox: bool = False
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalConversationDetail(ClinicalConversationSummary):
    messages: list[ClinicalMessageResponse]


class ShadowReviewResponse(BaseModel):
    id: int
    clinic_id: int
    conversation_id: int
    patient_message_id: int
    draft_reply: str
    intent: str
    confidence_score: float
    risk_reason: str
    status: str
    persona_name: str | None = None
    channel: str | None = None
    final_reply: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ShadowReviewDecisionRequest(BaseModel):
    status: str = Field(pattern="^(approved|edited|rejected)$")
    final_reply: str | None = Field(default=None, max_length=2000)


class ClinicalMetricsResponse(BaseModel):
    clinic_name: str
    conversations_today: int
    total_conversations: int
    pending_shadow_reviews: int
    doctor_inbox_count: int
    phone_calls_today: int
    auto_reply_rate: float
    appointments_pending: int
    reminders_due: int
    frustration_events: int


class ClinicalOverviewResponse(BaseModel):
    metrics: ClinicalMetricsResponse
    conversations: list[ClinicalConversationSummary]
    doctor_inbox: list[ClinicalConversationSummary]
    shadow_reviews: list[ShadowReviewResponse]


class ClinicalComplianceProfileResponse(BaseModel):
    clinic_id: int
    clinic_name: str
    data_residency_default: str
    external_transfer_allowed: bool
    processor_inventory: list[dict]
    production_modes: list[dict]
    mandatory_controls: list[str]
    blocked_by_default: list[str]
    operator_review_triggers: list[str]


class ClinicalPatentDossierResponse(BaseModel):
    working_title: str
    technical_field: str
    problem: str
    solution_summary: str
    candidate_independent_claims: list[str]
    candidate_dependent_claims: list[str]
    figures_to_prepare: list[str]
    evidence_to_preserve: list[str]
    next_actions: list[str]


class ClinicalSlotBoardResponse(BaseModel):
    summary: dict
    schedule: list[dict]
    acceptance_rules: list[dict]
    test_scenarios: list[dict]


class SimulateWhatsAppRequest(BaseModel):
    from_phone: str = Field(min_length=6, max_length=40)
    body: str = Field(min_length=1, max_length=2000)
    patient_name: str | None = Field(default=None, max_length=160)


class WebhookIngestionResponse(BaseModel):
    ok: bool
    clinic_id: int
    patient_id: int
    conversation_id: int
    message_id: int
    action: str
    reply: str | None = None
    shadow_review_id: int | None = None


class ClinicalPersonaResponse(BaseModel):
    id: str
    display_name: str
    role: str
    voice: str
    tone: str
    specialty: str
    safety_rule: str


class ClinicalAppointmentResponse(BaseModel):
    id: int
    clinic_id: int
    patient_id: int
    conversation_id: int | None = None
    department: str
    starts_at: datetime | None = None
    status: str
    notes: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalAppointmentCreateRequest(BaseModel):
    conversation_id: int
    department: str = Field(default="Muayene", min_length=2, max_length=140)
    starts_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VoiceCallSimulationRequest(BaseModel):
    from_phone: str = Field(min_length=6, max_length=40)
    speech: str = Field(min_length=1, max_length=2000)
    patient_name: str | None = Field(default=None, max_length=160)
    persona_id: str | None = Field(default=None, pattern="^(selin|arzu|can)$")
