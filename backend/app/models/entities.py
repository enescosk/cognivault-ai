from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, JSON, String, Text, func
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
