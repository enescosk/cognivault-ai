from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RoleName(str, Enum):
    CUSTOMER = "customer"
    OPERATOR = "operator"
    ADMIN = "admin"


class MessageSender(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AppointmentStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class AuditResultStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


class EnterpriseSessionStatus(str, Enum):
    ACTIVE = "active"
    NEEDS_HUMAN = "needs_human"
    CLOSED = "closed"


class EnterpriseTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    CLOSED = "closed"


class IntelligenceSourceKind(str, Enum):
    MANUAL = "manual"
    WEBSITE = "website"
    GOOGLE_PLACES = "google_places"
    X_API = "x_api"
    REDDIT_API = "reddit_api"
    CRM = "crm"


class IntelligenceJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class LeadContactKind(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    URL = "url"
    SOCIAL = "social"


class OutreachDraftStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"


class ClinicUserRole(str, Enum):
    OWNER = "owner"
    OPERATOR = "operator"
    CLINICIAN = "clinician"


class ClinicChannel(str, Enum):
    WHATSAPP = "whatsapp"
    WEB_CHAT = "web_chat"
    PHONE = "phone"
    MANUAL = "manual"


class ClinicConversationStatus(str, Enum):
    ACTIVE = "active"
    WAITING_HUMAN = "waiting_human"
    APPOINTMENT_PENDING = "appointment_pending"
    CLOSED = "closed"


class ClinicMessageSender(str, Enum):
    PATIENT = "patient"
    ASSISTANT = "assistant"
    OPERATOR = "operator"
    SYSTEM = "system"


class ClinicIntent(str, Enum):
    BOOK_APPOINTMENT = "book_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    ASK_PRICE = "ask_price"
    ASK_INSURANCE = "ask_insurance"
    ASK_LOCATION = "ask_location"
    ASK_WORKING_HOURS = "ask_working_hours"
    MEDICAL_EMERGENCY = "medical_emergency"
    GENERAL_QUESTION = "general_question"
    UNKNOWN = "unknown"


class ShadowReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ClinicalAppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ReminderStatus(str, Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"


class ConsentType(str, Enum):
    """KVKK Md. 5/6 kapsamında hastadan alınacak açık rıza tipleri.

    Her rıza tipi ayrı satır olarak kaydedilir; geri çekme `withdrawn_at` ile
    işaretlenir. Aynı hasta için aynı tipte birden çok satır olabilir — en
    son `granted_at` baz alınır.
    """

    VOICE_RECORDING = "voice_recording"           # Ses kaydının harici STT/TTS'e gönderilmesi
    DATA_PROCESSING = "data_processing"           # Ad-soyad, iletişim, sağlık şikayeti işleme
    CROSS_BORDER_TRANSFER = "cross_border_transfer"  # Yurt dışı veri transferi
    INSURANCE_LOOKUP = "insurance_lookup"         # Sigorta / SGK sorgusu


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    default_language: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(120))
    emergency_disclaimer: Mapped[str] = mapped_column(
        Text,
        default="This may be urgent. Please call emergency services or go to the nearest emergency department.",
        nullable=False,
    )
    ai_auto_reply_threshold: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    shadow_review_threshold: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    settings_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    branches: Mapped[list["ClinicBranch"]] = relationship(back_populates="clinic")
    memberships: Mapped[list["ClinicMembership"]] = relationship(back_populates="clinic")
    patients: Mapped[list["ClinicPatient"]] = relationship(back_populates="clinic")
    conversations: Mapped[list["ClinicConversation"]] = relationship(back_populates="clinic")


class ClinicBranch(Base):
    __tablename__ = "clinic_branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(40))
    working_hours_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clinic: Mapped["Clinic"] = relationship(back_populates="branches")


class ClinicMembership(Base):
    __tablename__ = "clinic_memberships"
    __table_args__ = (UniqueConstraint("clinic_id", "user_id", name="uq_clinic_membership_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[ClinicUserRole] = mapped_column(SqlEnum(ClinicUserRole), default=ClinicUserRole.OPERATOR, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clinic: Mapped["Clinic"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship()


class ClinicPatient(Base):
    __tablename__ = "clinic_patients"
    __table_args__ = (UniqueConstraint("clinic_id", "phone", name="uq_clinic_patient_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)
    source: Mapped[ClinicChannel] = mapped_column(SqlEnum(ClinicChannel), default=ClinicChannel.WHATSAPP, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    # KVKK retention policy — 10 yıl sonra otomatik anonymization tetiklenmeli (cron job)
    data_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    clinic: Mapped["Clinic"] = relationship(back_populates="patients")
    conversations: Mapped[list["ClinicConversation"]] = relationship(back_populates="patient")


class ClinicConversation(Base):
    __tablename__ = "clinic_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("clinic_patients.id"), nullable=False, index=True)
    channel: Mapped[ClinicChannel] = mapped_column(SqlEnum(ClinicChannel), default=ClinicChannel.WHATSAPP, nullable=False)
    status: Mapped[ClinicConversationStatus] = mapped_column(
        SqlEnum(ClinicConversationStatus), default=ClinicConversationStatus.ACTIVE, nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)
    intent: Mapped[ClinicIntent | None] = mapped_column(SqlEnum(ClinicIntent))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    last_patient_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_thread_id: Mapped[str | None] = mapped_column(String(160), index=True)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    # KVKK retention policy — 10 yıl sonra mesaj içerikleri anonymization sürecine girer
    data_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    clinic: Mapped["Clinic"] = relationship(back_populates="conversations")
    patient: Mapped["ClinicPatient"] = relationship(back_populates="conversations")
    messages: Mapped[list["ClinicMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ClinicMessage.created_at"
    )
    shadow_reviews: Mapped[list["ShadowReview"]] = relationship(back_populates="conversation")


class ClinicMessage(Base):
    __tablename__ = "clinic_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("clinic_conversations.id"), nullable=False, index=True)
    sender: Mapped[ClinicMessageSender] = mapped_column(SqlEnum(ClinicMessageSender), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)
    intent: Mapped[ClinicIntent | None] = mapped_column(SqlEnum(ClinicIntent))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    external_message_id: Mapped[str | None] = mapped_column(String(160), index=True)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped["ClinicConversation"] = relationship(back_populates="messages")


class ShadowReview(Base):
    __tablename__ = "shadow_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("clinic_conversations.id"), nullable=False, index=True)
    patient_message_id: Mapped[int] = mapped_column(ForeignKey("clinic_messages.id"), nullable=False)
    draft_reply: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[ClinicIntent] = mapped_column(SqlEnum(ClinicIntent), default=ClinicIntent.UNKNOWN, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ShadowReviewStatus] = mapped_column(
        SqlEnum(ShadowReviewStatus), default=ShadowReviewStatus.PENDING, nullable=False
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_reply: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation: Mapped["ClinicConversation"] = relationship(back_populates="shadow_reviews")
    patient_message: Mapped["ClinicMessage"] = relationship(foreign_keys=[patient_message_id])
    reviewed_by: Mapped["User"] = relationship()


class ClinicalAppointment(Base):
    __tablename__ = "clinical_appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("clinic_patients.id"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_conversations.id"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_branches.id"))
    department: Mapped[str] = mapped_column(String(140), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ClinicalAppointmentStatus] = mapped_column(
        SqlEnum(ClinicalAppointmentStatus), default=ClinicalAppointmentStatus.PENDING, nullable=False
    )
    external_ref: Mapped[str | None] = mapped_column(String(140))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PreIntake(Base):
    __tablename__ = "pre_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("clinic_patients.id"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_conversations.id"))
    answers_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("clinical_appointments.id"), nullable=False, index=True)
    channel: Mapped[ClinicChannel] = mapped_column(SqlEnum(ClinicChannel), default=ClinicChannel.WHATSAPP, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(SqlEnum(ReminderStatus), default=ReminderStatus.SCHEDULED, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InboundEvent(Base):
    """Idempotency record for inbound provider webhooks (Twilio, Meta, etc.).

    The unique constraint on (provider, external_id) means a duplicated webhook
    delivery is rejected at the DB layer instead of producing a duplicate
    `ClinicMessage` row.
    """

    __tablename__ = "inbound_events"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_inbound_events_provider_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)


class AgentDecisionLog(Base):
    """Structured record of every AI / human-in-the-loop decision in the system.

    Unifies what previously lived only in `ClinicMessage.metadata_json` and
    `ShadowReview.metadata_json`. Every decision is tenant-scoped via
    organization_id / clinic_id so operators can audit per-tenant agent
    behaviour, and the request_id ties it back to the originating HTTP call.
    """

    __tablename__ = "agent_decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk: Mapped[str] = mapped_column(String(20), default="low", nullable=False, index=True)
    requires_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    action: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(String(255))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id"), nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_conversations.id"), nullable=True, index=True)
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConsentRecord(Base):
    """KVKK Md. 5/6 açık rıza kaydı — her rıza/geri-çekme ayrı satır olarak tutulur.

    KVKK ispat yükü işleyene (klinik) ait olduğu için bu tablo append-only
    yaklaşımıyla yönetilir: rızayı geri çekme ayrı bir satır olarak değil,
    ilgili satıra `withdrawn_at` damgalanarak yapılır. `consent_text_version`
    hangi aydınlatma metninin kabul edildiğini izlemek için zorunludur — metin
    güncellendiğinde önceki sürümler hâlâ denetlenebilir kalır.
    """

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_patients.id"), nullable=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_conversations.id"), nullable=True, index=True)
    consent_type: Mapped[ConsentType] = mapped_column(SqlEnum(ConsentType), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    channel: Mapped[ClinicChannel | None] = mapped_column(SqlEnum(ClinicChannel), nullable=True)
    # IP veya cihaz parmak izi — denetim izi için (zorunlu değil)
    ip_or_device_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Hangi aydınlatma metninin kabul edildiği — semver veya tarih (örn. "v1.2.0" veya "2026-05-25")
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)


class BillingPlanTier(str, Enum):
    """Plan kademeleri — gerçek SaaS fiyatlandırma yapıldığında genişletilir."""
    STARTER = "starter"      # tek klinik, sınırlı kullanım
    GROWTH = "growth"        # birden fazla klinik, makul kotalar
    ENTERPRISE = "enterprise"  # custom limits, SSO, BAA
    INTERNAL = "internal"    # demo/test/dahili — fatura yok


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    TRIAL = "trial"


class BillingPlan(Base):
    """Statik plan kataloğu — limit/fiyat değişince yeni satır eklenir.

    Tarihsel `Subscription` satırları `plan_id` üzerinden eski plana sabitlenir;
    eski plan satırı silinmez, sadece `is_active=False` yapılır.
    """

    __tablename__ = "billing_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[BillingPlanTier] = mapped_column(SqlEnum(BillingPlanTier), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    monthly_price_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Kotalar — Subscription kullanım hesaplamasında baz alınır
    max_conversations_per_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_voice_minutes_per_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_llm_cost_usd_per_month: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    features_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Subscription(Base):
    """Bir organizasyonun aktif aboneliği — her org'da en fazla bir ACTIVE satır."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("billing_plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(SubscriptionStatus), default=SubscriptionStatus.TRIAL, nullable=False, index=True
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True)   # Stripe sub id vb.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UsageRecord(Base):
    """Saatlik / günlük kullanım kayıtları — kota hesaplamasında baz.

    `LlmUsageRecord`'tan farkı: bu tablo agregat (saatlik özet) tutar ve
    quota enforcement'a hizmet eder. LlmUsageRecord her bir LLM çağrısının
    detayı; UsageRecord her tipte sayaç (konuşma, ses dakikası, agent kullanımı).
    """

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)   # "conversations", "voice_minutes", "llm_cost_usd"
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboxEventStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class OutboxEvent(Base):
    """Transactional Outbox Pattern — atomik mesaj garanti hattı.

    Klinik mesajı / WhatsApp cevabı / e-posta gibi outbound aksiyonlar
    doğrudan dış servise gönderilmez. Önce bu tabloya **aynı işlem bloğunda**
    yazılır; bir background dispatcher tablodaki PENDING satırları okuyup
    gerçekten gönderir. Bu sayede DB commit ile dış API çağrısı arasında
    "dual-write" problemi (biri başarılı + diğeri çök) imkansızdır.

    `attempts` her retry'da artar; `max_attempts` dolduğunda satır
    DEAD_LETTER işaretlenir ve manuel inceleme bekler. `next_retry_at`
    exponential backoff için kullanılır.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    status: Mapped[OutboxEventStatus] = mapped_column(
        SqlEnum(OutboxEventStatus), default=OutboxEventStatus.PENDING, nullable=False, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id"), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class LlmUsageRecord(Base):
    """Per-call token + cost telemetry for every LLM invocation.

    Captures both successful and failed calls. `estimated_cost_usd` is computed
    at write-time from the static pricing table in `app.services.llm_pricing`,
    so historical rows survive future model price changes.
    """

    __tablename__ = "llm_usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)   # "openai" | "anthropic"
    model: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    agent_type: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class FrustrationLog(Base):
    __tablename__ = "frustration_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("clinic_conversations.id"))
    trigger: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    message_excerpt: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[RoleName] = mapped_column(SqlEnum(RoleName), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    department: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120))
    # Kullanıcının kayıtlı telefon numarası — randevu akışında otomatik doldurulur.
    # İlk randevuda istenir, sonraki sefer "kayıtlı numarandan onay göndereyim mi?" diye sorulur.
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role: Mapped["Role"] = relationship(back_populates="users")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
    appointments: Mapped[list["Appointment"]] = relationship(foreign_keys="Appointment.user_id", back_populates="user")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New workflow")
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    workflow_state: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    sender: Mapped[MessageSender] = mapped_column(SqlEnum(MessageSender), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    @property
    def appointment(self) -> dict | None:
        metadata = self.metadata_json or {}
        if metadata.get("type") != "appointment_confirmation":
            return None
        return {
            "confirmation_code": metadata.get("confirmation_code"),
            "department": metadata.get("department"),
            "scheduled_at": metadata.get("scheduled_at"),
            "location": metadata.get("location"),
            "contact_phone": metadata.get("contact_phone"),
            "status": metadata.get("status"),
        }


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="Remote")
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[int] = mapped_column(ForeignKey("appointment_slots.id"), nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        SqlEnum(AppointmentStatus), default=AppointmentStatus.CONFIRMED, nullable=False
    )
    confirmation_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="appointments")
    slot: Mapped["AppointmentSlot"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="SET NULL"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id"), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(120))
    result_status: Mapped[AuditResultStatus] = mapped_column(
        SqlEnum(AuditResultStatus), default=AuditResultStatus.INFO, nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    explanation: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    departments: Mapped[list["Department"]] = relationship(back_populates="organization")
    agents: Mapped[list["EnterpriseAgent"]] = relationship(back_populates="organization")
    customers: Mapped[list["EnterpriseCustomer"]] = relationship(back_populates="organization")
    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="organization")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="departments")
    agents: Mapped[list["EnterpriseAgent"]] = relationship(back_populates="department")
    tickets: Mapped[list["EnterpriseTicket"]] = relationship(back_populates="department")
    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="department")


class EnterpriseAgent(Base):
    __tablename__ = "enterprise_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    display_name: Mapped[str] = mapped_column(String(140), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(40), default="available", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="agents")
    user: Mapped["User"] = relationship()
    department: Mapped["Department"] = relationship(back_populates="agents")


class EnterpriseCustomer(Base):
    __tablename__ = "enterprise_customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(140), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    external_ref: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="customers")
    sessions: Mapped[list["EnterpriseSession"]] = relationship(back_populates="customer")
    tickets: Mapped[list["EnterpriseTicket"]] = relationship(back_populates="customer")


class EnterpriseSession(Base):
    __tablename__ = "enterprise_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("enterprise_customers.id"), nullable=False)
    chat_session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    channel: Mapped[str] = mapped_column(String(40), default="web_chat", nullable=False)
    status: Mapped[EnterpriseSessionStatus] = mapped_column(
        SqlEnum(EnterpriseSessionStatus), default=EnterpriseSessionStatus.ACTIVE, nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    handoff_package: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    metadata_json: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship()
    customer: Mapped["EnterpriseCustomer"] = relationship(back_populates="sessions")
    chat_session: Mapped["ChatSession"] = relationship()
    department: Mapped["Department"] = relationship()
    tickets: Mapped[list["EnterpriseTicket"]] = relationship(back_populates="session")


class EnterpriseTicket(Base):
    __tablename__ = "enterprise_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("enterprise_customers.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_sessions.id", ondelete="SET NULL"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_agents.id"))
    intent: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EnterpriseTicketStatus] = mapped_column(
        SqlEnum(EnterpriseTicketStatus), default=EnterpriseTicketStatus.OPEN, nullable=False
    )
    priority: Mapped[str] = mapped_column(String(30), default="normal", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    handoff_package: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship()
    customer: Mapped["EnterpriseCustomer"] = relationship(back_populates="tickets")
    session: Mapped["EnterpriseSession"] = relationship(back_populates="tickets")
    department: Mapped["Department"] = relationship(back_populates="tickets")
    assigned_agent: Mapped["EnterpriseAgent"] = relationship()


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    intent: Mapped[str] = mapped_column(String(120), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence_boost: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="routing_rules")
    department: Mapped["Department"] = relationship(back_populates="routing_rules")


class IntelligenceSource(Base):
    __tablename__ = "intelligence_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    kind: Mapped[IntelligenceSourceKind] = mapped_column(SqlEnum(IntelligenceSourceKind), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    policy: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    jobs: Mapped[list["IntelligenceJob"]] = relationship(back_populates="source")


class IntelligenceJob(Base):
    __tablename__ = "intelligence_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("intelligence_sources.id"), nullable=False)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    target_location: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[IntelligenceJobStatus] = mapped_column(
        SqlEnum(IntelligenceJobStatus), default=IntelligenceJobStatus.QUEUED, nullable=False
    )
    max_results: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source: Mapped["IntelligenceSource"] = relationship(back_populates="jobs")
    requested_by: Mapped["User"] = relationship()
    leads: Mapped[list["Lead"]] = relationship(back_populates="job")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("intelligence_jobs.id"), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(700))
    source_kind: Mapped[IntelligenceSourceKind] = mapped_column(SqlEnum(IntelligenceSourceKind), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consent_basis: Mapped[str] = mapped_column(String(80), default="public_business_listing", nullable=False)
    provenance: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    job: Mapped["IntelligenceJob"] = relationship(back_populates="leads")
    contact_points: Mapped[list["LeadContactPoint"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    outreach_drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="lead")


class LeadContactPoint(Base):
    __tablename__ = "lead_contact_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), nullable=False)
    kind: Mapped[LeadContactKind] = mapped_column(SqlEnum(LeadContactKind), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(80))
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(700))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lead: Mapped["Lead"] = relationship(back_populates="contact_points")


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutreachDraftStatus] = mapped_column(
        SqlEnum(OutreachDraftStatus), default=OutreachDraftStatus.DRAFT, nullable=False
    )
    metadata_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lead: Mapped["Lead"] = relationship(back_populates="outreach_drafts")
    created_by: Mapped["User"] = relationship()
