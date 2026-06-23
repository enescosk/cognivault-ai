from datetime import datetime
from typing import Literal

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
    last_urgency: str | None = None
    doctor_summary: str | None = None
    possible_conditions: list[dict] = Field(default_factory=list)
    appointment_draft: dict | None = None
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
    assigned_doctor_id: int | None = None
    assigned_doctor_name: str | None = None
    assigned_doctor_specialty: str | None = None
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
    triage_reviews: int
    emergency_reviews: int
    same_day_reviews: int
    doctor_inbox_count: int
    phone_calls_today: int
    whatsapp_threads_today: int
    auto_reply_rate: float
    appointments_pending: int
    reminders_due: int
    frustration_events: int


class ClinicalViewerResponse(BaseModel):
    clinic_role: str
    doctor_id: int | None = None
    doctor_name: str | None = None
    specialty: str | None = None


class ClinicalOverviewResponse(BaseModel):
    viewer: ClinicalViewerResponse
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
    # KVKK Md. 7 saklama politikası — admin paneli ve denetim için yapılandırılmış kayıt
    retention_policy: dict | None = None


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
    appointment_id: int | None = None


class ClinicalPersonaResponse(BaseModel):
    id: str
    display_name: str
    role: str
    voice: str
    tone: str
    specialty: str
    safety_rule: str


class ClinicDoctorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    branch_id: int | None = None
    full_name: str
    email: str
    specialty: str
    title: str
    bio: str | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClinicDoctorSlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    clinic_id: int
    start_time: datetime
    end_time: datetime
    is_booked: bool
    is_blocked: bool
    doctor_name: str | None = None
    specialty: str | None = None


class ClinicalProcedureInput(BaseModel):
    id: int | None = None
    name: str = Field(min_length=2, max_length=240)
    code: str | None = Field(default=None, max_length=80)
    tooth: str | None = Field(default=None, max_length=40)
    status: Literal["planned", "in_progress", "completed", "cancelled"] = "planned"
    notes: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(default=0, ge=0, le=1000)


class ClinicalProcedureResponse(BaseModel):
    id: int
    name: str
    code: str | None = None
    tooth: str | None = None
    status: str
    notes: str | None = None
    sort_order: int
    performed_by_doctor_id: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ClinicalAppointmentResponse(BaseModel):
    id: int
    clinic_id: int
    patient_id: int
    conversation_id: int | None = None
    doctor_id: int | None = None
    slot_id: int | None = None
    assigned_doctor_id: int | None = None
    assigned_doctor_name: str | None = None
    department: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    duration_minutes: int = 30
    visit_reason: str | None = None
    status: str
    notes: str | None = None
    doctor_name: str | None = None
    metadata_json: dict | None = None
    procedures: list[ClinicalProcedureResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ClinicalAppointmentCreateRequest(BaseModel):
    conversation_id: int
    department: str = Field(default="Muayene", min_length=2, max_length=140)
    doctor_id: int | None = None
    slot_id: int | None = None
    starts_at: datetime | None = None
    duration_minutes: int = Field(default=30, ge=15, le=240)
    visit_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class ClinicalAppointmentRow(BaseModel):
    """Operatör randevu listesi satırı — kim / ne zaman / nerede zenginleştirilmiş."""

    id: int
    patient_id: int
    patient_name: str | None = None
    patient_phone: str | None = None
    conversation_id: int | None = None
    assigned_doctor_id: int | None = None
    department: str
    physician_name: str | None = None
    branch_name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    duration_minutes: int = 30
    visit_reason: str | None = None
    status: str
    notes: str | None = None
    procedures: list[ClinicalProcedureResponse] = Field(default_factory=list)
    created_at: datetime


class ClinicalAppointmentStatusUpdate(BaseModel):
    status: Literal["pending", "confirmed", "cancelled"]


class ClinicalAppointmentDetailsUpdate(BaseModel):
    starts_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    visit_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)
    procedures: list[ClinicalProcedureInput] | None = Field(default=None, max_length=30)


class ClinicalManualAppointmentRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    phone: str = Field(min_length=6, max_length=40)
    department: str = Field(default="Muayene", min_length=2, max_length=140)
    starts_at: datetime | None = None
    duration_minutes: int = Field(default=30, ge=15, le=240)
    visit_reason: str | None = Field(default=None, max_length=500)
    physician_name: str | None = Field(default=None, max_length=160)
    branch_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class VoiceCallSimulationRequest(BaseModel):
    from_phone: str = Field(min_length=6, max_length=40)
    speech: str = Field(min_length=1, max_length=2000)
    patient_name: str | None = Field(default=None, max_length=160)
    persona_id: str | None = Field(default=None, pattern="^(selin|arzu|can)$")


class PreIntakeCreateRequest(BaseModel):
    patient_id: int
    conversation_id: int | None = None
    answers: dict = Field(default_factory=dict)
    is_complete: bool = False


class PreIntakeUpdateRequest(BaseModel):
    answers: dict | None = None
    is_complete: bool | None = None
    replace: bool = Field(
        default=False,
        description="When false (default), `answers` is merged into the existing answers; when true, it replaces them entirely.",
    )


class PreIntakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    patient_id: int
    conversation_id: int | None = None
    answers_json: dict
    is_complete: bool
    created_at: datetime
    updated_at: datetime
