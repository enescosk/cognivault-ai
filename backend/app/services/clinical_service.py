from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from urllib.parse import parse_qs

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import (
    Clinic,
    ClinicBranch,
    ClinicChannel,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicMembership,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ClinicUserRole,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    FrustrationLog,
    InboundEvent,
    PreIntake,
    RoleName,
    ShadowReview,
    ShadowReviewStatus,
    User,
)
from app.services.agents import AgentType, DecisionRisk, build_decision, record_agent_decision
from app.services.clinical_ai_service import detect_frustration, detect_language, generate_clinical_reply


@dataclass(frozen=True)
class IncomingClinicalMessage:
    from_phone: str
    body: str
    channel: ClinicChannel = ClinicChannel.WHATSAPP
    patient_name: str | None = None
    external_message_id: str | None = None
    external_thread_id: str | None = None
    requested_persona_id: str | None = None
    raw_payload: dict | None = None


@dataclass(frozen=True)
class IngestionResult:
    clinic: Clinic
    patient: ClinicPatient
    conversation: ClinicConversation
    message: ClinicMessage
    action: str
    reply: str | None = None
    shadow_review: ShadowReview | None = None


def normalize_phone(value: str) -> str:
    phone = value.strip()
    if phone.startswith("whatsapp:"):
        phone = phone.removeprefix("whatsapp:")
    if phone.startswith("client:"):
        phone = phone.removeprefix("client:")
    return phone.replace(" ", "")


def parse_twilio_form(body: bytes) -> IncomingClinicalMessage:
    parsed = parse_qs(body.decode("utf-8"))
    from_phone = parsed.get("From", [""])[0]
    message_body = parsed.get("Body", [""])[0]
    profile_name = parsed.get("ProfileName", [None])[0]
    message_sid = parsed.get("MessageSid", [None])[0]
    if not from_phone or not message_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Twilio WhatsApp fields")
    return IncomingClinicalMessage(
        from_phone=normalize_phone(from_phone),
        body=message_body.strip(),
        channel=ClinicChannel.WHATSAPP,
        patient_name=profile_name,
        external_message_id=message_sid,
        external_thread_id=normalize_phone(from_phone),
        raw_payload={key: values[0] if values else None for key, values in parsed.items()},
    )


def parse_meta_payload(payload: dict) -> list[IncomingClinicalMessage]:
    messages: list[IncomingClinicalMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {item.get("wa_id"): item.get("profile", {}).get("name") for item in value.get("contacts", [])}
            for item in value.get("messages", []):
                text = item.get("text", {}).get("body")
                from_phone = item.get("from")
                if not from_phone or not text:
                    continue
                messages.append(
                    IncomingClinicalMessage(
                        from_phone=normalize_phone(from_phone),
                        body=text.strip(),
                        channel=ClinicChannel.WHATSAPP,
                        patient_name=contacts.get(from_phone),
                        external_message_id=item.get("id"),
                        external_thread_id=normalize_phone(from_phone),
                        raw_payload=item,
                    )
                )
    return messages


def ensure_default_clinic(db: Session) -> Clinic:
    settings = get_settings()
    clinic = db.scalars(select(Clinic).where(Clinic.slug == settings.clinical_default_clinic_slug)).first()
    if clinic is not None:
        return clinic

    clinic = Clinic(
        name="Demo Klinik",
        slug=settings.clinical_default_clinic_slug,
        default_language="tr",
        ai_auto_reply_threshold=settings.clinical_auto_reply_threshold,
        shadow_review_threshold=settings.clinical_shadow_threshold,
        settings_json={
            "pricing_policy": "Prices vary by department and clinician.",
            "kvkk_note": "Demo data only; production requires Turkish hosting and DPA review.",
        },
    )
    db.add(clinic)
    db.flush()
    db.add(
        ClinicBranch(
            clinic_id=clinic.id,
            name="Merkez Sube",
            address="Istanbul",
            phone="+90 212 000 00 00",
            working_hours_json={"weekdays": "09:00-18:00", "saturday": "10:00-14:00"},
        )
    )
    db.commit()
    db.refresh(clinic)
    return clinic


def ensure_clinic_access(db: Session, current_user: User) -> Clinic:
    if current_user.role.name not in {RoleName.OPERATOR, RoleName.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clinical dashboard requires operator access")

    clinic: Clinic | None = None
    if current_user.organization_id is not None:
        # Tenant-aware path: scope the visible clinic to the user's organisation.
        clinic = db.scalars(
            select(Clinic)
            .where(Clinic.organization_id == current_user.organization_id)
            .order_by(Clinic.id)
        ).first()
    if clinic is None:
        # Legacy single-tenant fallback for users that pre-date the org backfill.
        clinic = ensure_default_clinic(db)

    membership = db.scalars(
        select(ClinicMembership).where(
            ClinicMembership.clinic_id == clinic.id,
            ClinicMembership.user_id == current_user.id,
        )
    ).first()
    if membership is None:
        db.add(
            ClinicMembership(
                clinic_id=clinic.id,
                user_id=current_user.id,
                role=ClinicUserRole.OWNER if current_user.role.name == RoleName.ADMIN else ClinicUserRole.OPERATOR,
            )
        )
        db.commit()
    return clinic


def _find_or_create_patient(db: Session, clinic: Clinic, incoming: IncomingClinicalMessage) -> ClinicPatient:
    phone = normalize_phone(incoming.from_phone)
    patient = db.scalars(select(ClinicPatient).where(ClinicPatient.clinic_id == clinic.id, ClinicPatient.phone == phone)).first()
    if patient is not None:
        if incoming.patient_name and not patient.full_name:
            patient.full_name = incoming.patient_name
            db.add(patient)
            db.commit()
            db.refresh(patient)
        return patient

    language = detect_language(incoming.body, clinic.default_language)
    patient = ClinicPatient(
        clinic_id=clinic.id,
        full_name=incoming.patient_name,
        phone=phone,
        language=language,
        source=incoming.channel,
        external_ref=phone,
        metadata_json={},
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def _find_or_create_conversation(db: Session, clinic: Clinic, patient: ClinicPatient, incoming: IncomingClinicalMessage) -> ClinicConversation:
    conversation = db.scalars(
        select(ClinicConversation)
        .where(
            ClinicConversation.clinic_id == clinic.id,
            ClinicConversation.patient_id == patient.id,
            ClinicConversation.channel == incoming.channel,
            ClinicConversation.status.in_(
                [
                    ClinicConversationStatus.ACTIVE,
                    ClinicConversationStatus.WAITING_HUMAN,
                    ClinicConversationStatus.APPOINTMENT_PENDING,
                ]
            ),
        )
        .order_by(ClinicConversation.updated_at.desc())
    ).first()
    if conversation is not None:
        return conversation

    conversation = ClinicConversation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        channel=incoming.channel,
        language=patient.language,
        external_thread_id=incoming.external_thread_id or patient.phone,
        metadata_json={},
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _provider_from_channel(channel: ClinicChannel) -> str:
    if channel == ClinicChannel.WHATSAPP:
        return "whatsapp"
    if channel == ClinicChannel.PHONE:
        return "voice"
    return channel.value


def _existing_inbound_message(
    db: Session, clinic: Clinic, provider: str, external_id: str
) -> ClinicMessage | None:
    return db.scalars(
        select(ClinicMessage)
        .where(
            ClinicMessage.clinic_id == clinic.id,
            ClinicMessage.external_message_id == external_id,
        )
        .order_by(ClinicMessage.created_at.desc())
    ).first()


def ingest_clinical_message(db: Session, incoming: IncomingClinicalMessage, clinic: Clinic | None = None) -> IngestionResult:
    clinic = clinic or ensure_default_clinic(db)

    if incoming.external_message_id:
        provider = _provider_from_channel(incoming.channel)
        existing_event = db.scalars(
            select(InboundEvent).where(
                InboundEvent.provider == provider,
                InboundEvent.external_id == incoming.external_message_id,
            )
        ).first()
        if existing_event is not None:
            existing_message = _existing_inbound_message(
                db, clinic, provider, incoming.external_message_id
            )
            if existing_message is not None:
                conversation = db.get(ClinicConversation, existing_message.conversation_id)
                patient = db.get(ClinicPatient, conversation.patient_id) if conversation else None
                if conversation is not None and patient is not None:
                    return IngestionResult(
                        clinic=clinic,
                        patient=patient,
                        conversation=conversation,
                        message=existing_message,
                        action="duplicate_ignored",
                        reply=None,
                        shadow_review=None,
                    )
        db.add(
            InboundEvent(
                clinic_id=clinic.id,
                provider=provider,
                external_id=incoming.external_message_id,
                payload_json={"channel": incoming.channel.value, "from_phone": incoming.from_phone},
            )
        )
        db.commit()

    patient = _find_or_create_patient(db, clinic, incoming)
    conversation = _find_or_create_conversation(db, clinic, patient, incoming)
    language = detect_language(incoming.body, patient.language or clinic.default_language)

    patient.language = language
    conversation.language = language
    conversation.last_patient_message_at = datetime.now(timezone.utc)
    conversation.status = ClinicConversationStatus.ACTIVE
    db.add(patient)
    db.add(conversation)
    db.commit()

    message = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender=ClinicMessageSender.PATIENT,
        content=incoming.body,
        language=language,
        external_message_id=incoming.external_message_id,
        metadata_json={"raw_payload": incoming.raw_payload or {}, "source": incoming.channel.value},
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    ai_result = generate_clinical_reply(clinic, incoming.body, language, incoming.requested_persona_id)
    conversation.intent = ai_result.intent
    conversation.confidence_score = ai_result.confidence
    conversation.metadata_json = {
        **(conversation.metadata_json or {}),
        "last_persona_id": ai_result.persona_id,
        "last_persona_name": ai_result.persona_name,
        "last_voice": ai_result.voice,
        "last_channel": incoming.channel.value,
    }

    if detect_frustration(incoming.body):
        db.add(
            FrustrationLog(
                clinic_id=clinic.id,
                conversation_id=conversation.id,
                trigger="patient_language",
                severity=2,
                message_excerpt=incoming.body[:500],
                metadata_json={"source_message_id": message.id, "channel": incoming.channel.value},
            )
        )

    needs_shadow = ai_result.requires_human_review or ai_result.confidence < clinic.ai_auto_reply_threshold
    if needs_shadow:
        conversation.status = ClinicConversationStatus.WAITING_HUMAN
        review = ShadowReview(
            clinic_id=clinic.id,
            conversation_id=conversation.id,
            patient_message_id=message.id,
            draft_reply=ai_result.reply,
            intent=ai_result.intent,
            confidence_score=ai_result.confidence,
            risk_reason=ai_result.risk_reason or "requires_human_review",
            metadata_json={
                "action": ai_result.action,
                "data": ai_result.data or {},
                "persona_id": ai_result.persona_id,
                "persona_name": ai_result.persona_name,
                "voice": ai_result.voice,
                "channel": incoming.channel.value,
                "doctor_inbox": True,
            },
        )
        db.add(conversation)
        db.add(review)
        db.commit()
        db.refresh(conversation)
        db.refresh(review)
        record_agent_decision(
            db,
            build_decision(
                agent_type=AgentType.ROUTING,
                intent=ai_result.intent.value if hasattr(ai_result.intent, "value") else str(ai_result.intent),
                confidence=ai_result.confidence,
                risk=DecisionRisk.HIGH,
                requires_human=True,
                action="shadow_review",
                reason=ai_result.risk_reason or "requires_human_review",
                organization_id=clinic.organization_id,
                payload={
                    "channel": incoming.channel.value,
                    "shadow_review_id": review.id,
                    "persona_id": ai_result.persona_id,
                },
            ),
            clinic_id=clinic.id,
            conversation_id=conversation.id,
        )
        return IngestionResult(
            clinic=clinic,
            patient=patient,
            conversation=conversation,
            message=message,
            action="shadow_review",
            shadow_review=review,
        )

    assistant_message = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender=ClinicMessageSender.ASSISTANT,
        content=ai_result.reply,
        language=language,
        intent=ai_result.intent,
        confidence_score=ai_result.confidence,
        metadata_json={
            "action": ai_result.action,
            "delivery": "simulated",
            "persona_id": ai_result.persona_id,
            "persona_name": ai_result.persona_name,
            "voice": ai_result.voice,
            "channel": incoming.channel.value,
        },
    )
    db.add(assistant_message)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.SUPPORT,
            intent=ai_result.intent.value if hasattr(ai_result.intent, "value") else str(ai_result.intent),
            confidence=ai_result.confidence,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action=ai_result.action or "auto_reply",
            reason="confidence_above_threshold",
            organization_id=clinic.organization_id,
            payload={
                "channel": incoming.channel.value,
                "assistant_message_id": assistant_message.id,
                "persona_id": ai_result.persona_id,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=conversation.id,
    )
    return IngestionResult(
        clinic=clinic,
        patient=patient,
        conversation=conversation,
        message=message,
        action="auto_reply",
        reply=ai_result.reply,
    )


def list_clinical_conversations(db: Session, clinic: Clinic, limit: int = 30) -> list[ClinicConversation]:
    return list(
        db.scalars(
            select(ClinicConversation)
            .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
            .where(ClinicConversation.clinic_id == clinic.id)
            .order_by(ClinicConversation.updated_at.desc())
            .limit(limit)
        )
    )


def get_clinical_conversation(db: Session, clinic: Clinic, conversation_id: int) -> ClinicConversation:
    conversation = db.scalars(
        select(ClinicConversation)
        .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
        .where(ClinicConversation.clinic_id == clinic.id, ClinicConversation.id == conversation_id)
    ).first()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinical conversation not found")
    return conversation


def list_shadow_reviews(db: Session, clinic: Clinic, status_value: ShadowReviewStatus | None = ShadowReviewStatus.PENDING) -> list[ShadowReview]:
    query = select(ShadowReview).where(ShadowReview.clinic_id == clinic.id).order_by(ShadowReview.created_at.desc())
    if status_value is not None:
        query = query.where(ShadowReview.status == status_value)
    return list(db.scalars(query))


def list_doctor_inbox(db: Session, clinic: Clinic, limit: int = 30) -> list[ClinicConversation]:
    return list(
        db.scalars(
            select(ClinicConversation)
            .options(selectinload(ClinicConversation.patient), selectinload(ClinicConversation.messages))
            .where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.status.in_(
                    [
                        ClinicConversationStatus.WAITING_HUMAN,
                        ClinicConversationStatus.APPOINTMENT_PENDING,
                    ]
                ),
            )
            .order_by(ClinicConversation.updated_at.desc())
            .limit(limit)
        )
    )


def create_clinical_appointment_from_conversation(
    db: Session,
    clinic: Clinic,
    conversation_id: int,
    department: str,
    starts_at: datetime | None,
    notes: str | None = None,
) -> ClinicalAppointment:
    conversation = get_clinical_conversation(db, clinic, conversation_id)
    appointment = ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=conversation.patient_id,
        conversation_id=conversation.id,
        department=department.strip() or "Muayene",
        starts_at=starts_at,
        status=ClinicalAppointmentStatus.PENDING if starts_at is None else ClinicalAppointmentStatus.CONFIRMED,
        notes=notes,
        metadata_json={"created_from": "doctor_inbox"},
    )
    conversation.status = ClinicConversationStatus.APPOINTMENT_PENDING if starts_at is None else ClinicConversationStatus.ACTIVE
    db.add(appointment)
    db.add(conversation)
    db.commit()
    db.refresh(appointment)
    return appointment


def upcoming_clinical_appointments(db: Session, clinic: Clinic, within_minutes: int = 120) -> list[ClinicalAppointment]:
    now = datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(ClinicalAppointment)
            .where(
                ClinicalAppointment.clinic_id == clinic.id,
                ClinicalAppointment.status == ClinicalAppointmentStatus.CONFIRMED,
                ClinicalAppointment.starts_at.is_not(None),
                ClinicalAppointment.starts_at >= now,
                ClinicalAppointment.starts_at <= now + timedelta(minutes=within_minutes),
            )
            .order_by(ClinicalAppointment.starts_at.asc())
        )
    )


def update_shadow_review(
    db: Session,
    clinic: Clinic,
    current_user: User,
    review_id: int,
    status_value: str,
    final_reply: str | None,
) -> ShadowReview:
    review = db.scalars(select(ShadowReview).where(ShadowReview.clinic_id == clinic.id, ShadowReview.id == review_id)).first()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shadow review not found")

    next_status = ShadowReviewStatus(status_value)
    if next_status == ShadowReviewStatus.EDITED and not final_reply:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited review requires final_reply")

    review.status = next_status
    review.final_reply = final_reply or review.draft_reply
    review.reviewed_by_user_id = current_user.id
    review.reviewed_at = datetime.now(timezone.utc)

    conversation = get_clinical_conversation(db, clinic, review.conversation_id)
    if next_status in {ShadowReviewStatus.APPROVED, ShadowReviewStatus.EDITED}:
        db.add(
            ClinicMessage(
                clinic_id=clinic.id,
                conversation_id=conversation.id,
                sender=ClinicMessageSender.OPERATOR,
                content=review.final_reply,
                language=conversation.language,
                intent=review.intent,
                confidence_score=review.confidence_score,
                metadata_json={"shadow_review_id": review.id, "delivery": "simulated"},
            )
        )
        conversation.status = ClinicConversationStatus.ACTIVE
    elif next_status == ShadowReviewStatus.REJECTED:
        conversation.status = ClinicConversationStatus.WAITING_HUMAN

    db.add(review)
    db.add(conversation)
    db.commit()
    db.refresh(review)

    # Log the human-in-the-loop decision so it shows up alongside AI decisions.
    decision_intent = review.intent.value if hasattr(review.intent, "value") else str(review.intent)
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.ROUTING,
            intent=decision_intent,
            confidence=review.confidence_score,
            risk=DecisionRisk.HIGH if next_status == ShadowReviewStatus.REJECTED else DecisionRisk.MEDIUM,
            requires_human=True,
            action=f"shadow_review.{next_status.value}",
            reason="operator_review",
            organization_id=clinic.organization_id,
            payload={
                "review_id": review.id,
                "operator_user_id": current_user.id,
                "final_reply_used": review.final_reply,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
    )
    return review


def clinical_metrics(db: Session, clinic: Clinic) -> dict:
    today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    total_conversations = db.scalar(select(func.count(ClinicConversation.id)).where(ClinicConversation.clinic_id == clinic.id)) or 0
    conversations_today = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.created_at >= today_start,
            )
        )
        or 0
    )
    pending_shadow = (
        db.scalar(
            select(func.count(ShadowReview.id)).where(
                ShadowReview.clinic_id == clinic.id,
                ShadowReview.status == ShadowReviewStatus.PENDING,
            )
        )
        or 0
    )
    doctor_inbox_count = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.status.in_(
                    [ClinicConversationStatus.WAITING_HUMAN, ClinicConversationStatus.APPOINTMENT_PENDING]
                ),
            )
        )
        or 0
    )
    phone_calls_today = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.channel == ClinicChannel.PHONE,
                ClinicConversation.created_at >= today_start,
            )
        )
        or 0
    )
    assistant_messages = (
        db.scalar(
            select(func.count(ClinicMessage.id)).where(
                ClinicMessage.clinic_id == clinic.id,
                ClinicMessage.sender == ClinicMessageSender.ASSISTANT,
            )
        )
        or 0
    )
    patient_messages = (
        db.scalar(
            select(func.count(ClinicMessage.id)).where(
                ClinicMessage.clinic_id == clinic.id,
                ClinicMessage.sender == ClinicMessageSender.PATIENT,
            )
        )
        or 0
    )
    appointments_pending = (
        db.scalar(
            select(func.count(ClinicalAppointment.id)).where(
                ClinicalAppointment.clinic_id == clinic.id,
                ClinicalAppointment.status == ClinicalAppointmentStatus.PENDING,
            )
        )
        or 0
    )
    reminders_due = len(upcoming_clinical_appointments(db, clinic, within_minutes=120))
    frustration_events = db.scalar(select(func.count(FrustrationLog.id)).where(FrustrationLog.clinic_id == clinic.id)) or 0
    return {
        "clinic_name": clinic.name,
        "conversations_today": conversations_today,
        "total_conversations": total_conversations,
        "pending_shadow_reviews": pending_shadow,
        "doctor_inbox_count": doctor_inbox_count,
        "phone_calls_today": phone_calls_today,
        "auto_reply_rate": round(assistant_messages / patient_messages, 2) if patient_messages else 0.0,
        "appointments_pending": appointments_pending,
        "reminders_due": reminders_due,
        "frustration_events": frustration_events,
    }


def _get_clinic_patient(db: Session, clinic: Clinic, patient_id: int) -> ClinicPatient:
    patient = db.scalars(
        select(ClinicPatient).where(ClinicPatient.id == patient_id, ClinicPatient.clinic_id == clinic.id)
    ).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def create_pre_intake(
    db: Session,
    clinic: Clinic,
    patient_id: int,
    conversation_id: int | None = None,
    answers: dict | None = None,
    is_complete: bool = False,
) -> PreIntake:
    patient = _get_clinic_patient(db, clinic, patient_id)
    if conversation_id is not None:
        get_clinical_conversation(db, clinic, conversation_id)

    pre_intake = PreIntake(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=conversation_id,
        answers_json=dict(answers or {}),
        is_complete=is_complete,
    )
    db.add(pre_intake)
    db.commit()
    db.refresh(pre_intake)
    return pre_intake


def get_pre_intake(db: Session, clinic: Clinic, pre_intake_id: int) -> PreIntake:
    pre_intake = db.scalars(
        select(PreIntake).where(PreIntake.id == pre_intake_id, PreIntake.clinic_id == clinic.id)
    ).first()
    if pre_intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pre-intake not found")
    return pre_intake


def list_pre_intakes(
    db: Session,
    clinic: Clinic,
    patient_id: int | None = None,
    conversation_id: int | None = None,
    is_complete: bool | None = None,
    limit: int = 50,
) -> list[PreIntake]:
    stmt = select(PreIntake).where(PreIntake.clinic_id == clinic.id)
    if patient_id is not None:
        stmt = stmt.where(PreIntake.patient_id == patient_id)
    if conversation_id is not None:
        stmt = stmt.where(PreIntake.conversation_id == conversation_id)
    if is_complete is not None:
        stmt = stmt.where(PreIntake.is_complete == is_complete)
    stmt = stmt.order_by(PreIntake.updated_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def update_pre_intake(
    db: Session,
    clinic: Clinic,
    pre_intake_id: int,
    answers: dict | None = None,
    is_complete: bool | None = None,
    replace: bool = False,
) -> PreIntake:
    pre_intake = get_pre_intake(db, clinic, pre_intake_id)

    if answers is not None:
        if replace:
            pre_intake.answers_json = dict(answers)
        else:
            merged = dict(pre_intake.answers_json or {})
            merged.update(answers)
            pre_intake.answers_json = merged
    if is_complete is not None:
        pre_intake.is_complete = is_complete

    db.add(pre_intake)
    db.commit()
    db.refresh(pre_intake)

    answer_count = len(pre_intake.answers_json or {})
    record_agent_decision(
        db,
        build_decision(
            agent_type=AgentType.FORM,
            intent="pre_intake_progress",
            confidence=1.0 if pre_intake.is_complete else 0.5,
            risk=DecisionRisk.LOW,
            requires_human=False,
            action="persist_pre_intake" if pre_intake.is_complete else "ask_next_question",
            reason="form_complete" if pre_intake.is_complete else "form_in_progress",
            organization_id=clinic.organization_id,
            payload={
                "pre_intake_id": pre_intake.id,
                "answer_count": answer_count,
                "is_complete": pre_intake.is_complete,
                "replace_mode": replace,
            },
        ),
        clinic_id=clinic.id,
        conversation_id=pre_intake.conversation_id,
    )
    return pre_intake
