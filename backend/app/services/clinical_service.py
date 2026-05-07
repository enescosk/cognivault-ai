from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import re
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

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
    ClinicIntent,
    ClinicMessage,
    ClinicMessageSender,
    ClinicPatient,
    ClinicUserRole,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    FrustrationLog,
    RoleName,
    ShadowReview,
    ShadowReviewStatus,
    User,
)
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
    appointment: ClinicalAppointment | None = None


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


def _clinic_timezone(clinic: Clinic) -> ZoneInfo:
    try:
        return ZoneInfo(clinic.timezone or "Europe/Istanbul")
    except Exception:
        return ZoneInfo("Europe/Istanbul")


def _has_appointment_signal(text: str, intent: ClinicIntent) -> bool:
    lowered = text.lower()
    if intent == ClinicIntent.BOOK_APPOINTMENT:
        return True
    appointment_terms = {
        "randevu",
        "muayene",
        "kontrol",
        "doktor görebilir",
        "doktor gorebilir",
        "hekim görebilir",
        "hekim gorebilir",
        "yarın gelebilir",
        "yarin gelebilir",
        "bugün gelebilir",
        "bugun gelebilir",
    }
    return any(term in lowered for term in appointment_terms)


def _infer_department(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("implant", "dis", "diş", "kanal", "dolgu", "yirmilik", "20lik", "diş taşı", "dis tasi")):
        if "implant" in lowered:
            return "Implant degerlendirme"
        if "kanal" in lowered:
            return "Endodonti / kanal tedavisi"
        if "dolgu" in lowered:
            return "Restoratif dis tedavisi"
        if "diş taşı" in lowered or "dis tasi" in lowered:
            return "Dis tasi temizligi"
        return "Dis hekimligi muayenesi"
    if any(term in lowered for term in ("dermatoloji", "cilt", "ben kontrol", "leke", "dokuntu", "döküntü")):
        return "Dermatoloji muayenesi"
    if any(term in lowered for term in ("botoks", "estetik", "mezoterapi", "dolgu")):
        return "Estetik gorusme"
    return "Muayene"


def _next_weekday(base: datetime, target_weekday: int) -> datetime:
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def _infer_requested_start(text: str, clinic: Clinic) -> tuple[datetime | None, list[str]]:
    lowered = text.lower()
    tz = _clinic_timezone(clinic)
    now = datetime.now(tz)
    base_date: datetime | None = None
    inferred_fields: list[str] = []

    if "yarın" in lowered or "yarin" in lowered:
        base_date = now + timedelta(days=1)
        inferred_fields.append("day")
    elif "bugün" in lowered or "bugun" in lowered:
        base_date = now
        inferred_fields.append("day")
    else:
        weekdays = {
            "pazartesi": 0,
            "salı": 1,
            "sali": 1,
            "çarşamba": 2,
            "carsamba": 2,
            "perşembe": 3,
            "persembe": 3,
            "cuma": 4,
            "cumartesi": 5,
        }
        for label, weekday in weekdays.items():
            if label in lowered:
                base_date = _next_weekday(now, weekday)
                inferred_fields.append("weekday")
                break

    hour: int | None = None
    minute = 0
    for time_match in re.finditer(r"(?:saat\s*)?(\d{1,2})(?:[:.](\d{2}))?", lowered):
        candidate = int(time_match.group(1))
        if 7 <= candidate <= 21:
            hour = candidate
            minute = int(time_match.group(2) or 0)
            break
    if hour is None and base_date is not None:
        hour = 10
        inferred_fields.append("time_defaulted")

    if base_date is None or hour is None:
        return None, inferred_fields

    requested = datetime.combine(base_date.date(), time(hour=hour, minute=minute), tzinfo=tz)
    if requested <= now:
        requested = requested + timedelta(days=1)
    return requested.astimezone(timezone.utc), inferred_fields


def _appointment_draft_payload(appointment: ClinicalAppointment, missing_fields: list[str] | None = None) -> dict:
    return {
        "id": appointment.id,
        "department": appointment.department,
        "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
        "status": appointment.status.value,
        "missing_fields": missing_fields or (appointment.metadata_json or {}).get("missing_fields", []),
        "source": (appointment.metadata_json or {}).get("created_from", "conversation"),
    }


def _find_conversation_appointment(db: Session, clinic: Clinic, conversation: ClinicConversation) -> ClinicalAppointment | None:
    return db.scalars(
        select(ClinicalAppointment)
        .where(
            ClinicalAppointment.clinic_id == clinic.id,
            ClinicalAppointment.conversation_id == conversation.id,
            ClinicalAppointment.status.in_([ClinicalAppointmentStatus.PENDING, ClinicalAppointmentStatus.CONFIRMED]),
        )
        .order_by(ClinicalAppointment.created_at.desc())
    ).first()


def _create_or_update_appointment_draft(
    db: Session,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
    message: ClinicMessage,
    text: str,
    intent: ClinicIntent,
    doctor_summary: str | None,
) -> ClinicalAppointment | None:
    if intent == ClinicIntent.MEDICAL_EMERGENCY or not _has_appointment_signal(text, intent):
        return None

    requested_start, inferred_fields = _infer_requested_start(text, clinic)
    missing_fields: list[str] = []
    if requested_start is None:
        missing_fields.append("preferred_time")
    if not patient.full_name:
        missing_fields.append("patient_name")

    existing = _find_conversation_appointment(db, clinic, conversation)
    if existing is not None and existing.status == ClinicalAppointmentStatus.CONFIRMED:
        conversation.metadata_json = {
            **(conversation.metadata_json or {}),
            "appointment_draft": _appointment_draft_payload(existing),
        }
        return existing

    metadata = {
        "created_from": "ai_conversation_draft",
        "source_message_id": message.id,
        "patient_phrase": text[:500],
        "missing_fields": missing_fields,
        "inferred_fields": inferred_fields,
        "doctor_summary": doctor_summary,
    }

    appointment = existing or ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=conversation.id,
        department=_infer_department(text),
        status=ClinicalAppointmentStatus.PENDING,
        metadata_json={},
    )
    appointment.department = _infer_department(text)
    appointment.starts_at = requested_start
    appointment.status = ClinicalAppointmentStatus.PENDING
    appointment.notes = doctor_summary or f"Hasta talebi: {text[:500]}"
    appointment.metadata_json = {**(appointment.metadata_json or {}), **metadata}
    db.add(appointment)
    db.flush()

    conversation.metadata_json = {
        **(conversation.metadata_json or {}),
        "appointment_draft": _appointment_draft_payload(appointment, missing_fields),
    }
    return appointment


def ingest_clinical_message(db: Session, incoming: IncomingClinicalMessage, clinic: Clinic | None = None) -> IngestionResult:
    clinic = clinic or ensure_default_clinic(db)
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
    triage = ai_result.triage_assessment or {}
    doctor_summary = (ai_result.data or {}).get("doctor_summary")
    possible_conditions = (ai_result.data or {}).get("possible_conditions", [])
    message.intent = ai_result.intent
    message.confidence_score = ai_result.confidence
    message.metadata_json = {
        **(message.metadata_json or {}),
        "persona_id": ai_result.persona_id,
        "persona_name": ai_result.persona_name,
        "voice": ai_result.voice,
        "triage": triage or None,
        "doctor_summary": doctor_summary,
        "possible_conditions": possible_conditions,
    }
    conversation.intent = ai_result.intent
    conversation.confidence_score = ai_result.confidence
    conversation.metadata_json = {
        **(conversation.metadata_json or {}),
        "last_persona_id": ai_result.persona_id,
        "last_persona_name": ai_result.persona_name,
        "last_voice": ai_result.voice,
        "last_channel": incoming.channel.value,
        "last_urgency": triage.get("urgency"),
        "doctor_summary": doctor_summary,
        "possible_conditions": possible_conditions,
    }
    appointment = _create_or_update_appointment_draft(
        db,
        clinic,
        patient,
        conversation,
        message,
        incoming.body,
        ai_result.intent,
        doctor_summary,
    )

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
                "triage": triage or None,
                "doctor_summary": doctor_summary,
                "possible_conditions": possible_conditions,
            },
        )
        db.add(message)
        db.add(conversation)
        db.add(review)
        db.commit()
        db.refresh(conversation)
        db.refresh(review)
        return IngestionResult(
            clinic=clinic,
            patient=patient,
            conversation=conversation,
            message=message,
            action="shadow_review",
            shadow_review=review,
            appointment=appointment,
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
            "triage": triage or None,
            "doctor_summary": doctor_summary,
            "possible_conditions": possible_conditions,
        },
    )
    if appointment is not None:
        conversation.status = ClinicConversationStatus.APPOINTMENT_PENDING
    db.add(message)
    db.add(assistant_message)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return IngestionResult(
        clinic=clinic,
        patient=patient,
        conversation=conversation,
        message=message,
        action="auto_reply",
        reply=ai_result.reply,
        appointment=appointment,
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
    appointment = _find_conversation_appointment(db, clinic, conversation)
    if appointment is None:
        appointment = ClinicalAppointment(
            clinic_id=clinic.id,
            patient_id=conversation.patient_id,
            conversation_id=conversation.id,
            metadata_json={},
        )
    appointment.department = department.strip() or appointment.department or "Muayene"
    appointment.starts_at = starts_at
    appointment.status = ClinicalAppointmentStatus.PENDING if starts_at is None else ClinicalAppointmentStatus.CONFIRMED
    appointment.notes = notes
    appointment.metadata_json = {
        **(appointment.metadata_json or {}),
        "created_from": (appointment.metadata_json or {}).get("created_from", "doctor_inbox"),
        "confirmed_from": "doctor_inbox" if starts_at is not None else None,
    }
    conversation.status = ClinicConversationStatus.APPOINTMENT_PENDING if starts_at is None else ClinicConversationStatus.ACTIVE
    db.add(appointment)
    db.flush()
    conversation.metadata_json = {
        **(conversation.metadata_json or {}),
        "appointment_draft": _appointment_draft_payload(appointment),
    }
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
    return review


def clinical_metrics(db: Session, clinic: Clinic) -> dict:
    def review_urgency(review: ShadowReview) -> str | None:
        triage = (review.metadata_json or {}).get("triage")
        return triage.get("urgency") if isinstance(triage, dict) else None

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
    pending_review_items = list(
        db.scalars(
            select(ShadowReview).where(
                ShadowReview.clinic_id == clinic.id,
                ShadowReview.status == ShadowReviewStatus.PENDING,
            )
        )
    )
    pending_shadow = len(pending_review_items)
    triage_reviews = sum(1 for item in pending_review_items if item.intent in {ClinicIntent.SYMPTOM_TRIAGE, ClinicIntent.MEDICAL_EMERGENCY})
    emergency_reviews = sum(
        1
        for item in pending_review_items
        if review_urgency(item) == "emergency"
    )
    same_day_reviews = sum(
        1
        for item in pending_review_items
        if review_urgency(item) == "same_day"
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
    whatsapp_threads_today = (
        db.scalar(
            select(func.count(ClinicConversation.id)).where(
                ClinicConversation.clinic_id == clinic.id,
                ClinicConversation.channel == ClinicChannel.WHATSAPP,
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
        "triage_reviews": triage_reviews,
        "emergency_reviews": emergency_reviews,
        "same_day_reviews": same_day_reviews,
        "doctor_inbox_count": doctor_inbox_count,
        "phone_calls_today": phone_calls_today,
        "whatsapp_threads_today": whatsapp_threads_today,
        "auto_reply_rate": round(assistant_messages / patient_messages, 2) if patient_messages else 0.0,
        "appointments_pending": appointments_pending,
        "reminders_due": reminders_due,
        "frustration_events": frustration_events,
    }
