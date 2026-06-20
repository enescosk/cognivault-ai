from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    Clinic, ClinicChannel, ClinicConversation, ClinicConversationStatus, ClinicPatient,
    ClinicalAppointment, ClinicalAppointmentProcedure, ClinicalAppointmentStatus,
    ClinicalProcedureStatus, Doctor,
)


def _normalize_phone(value: str) -> str:
    phone = value.strip()
    if phone.startswith("whatsapp:"):
        phone = phone.removeprefix("whatsapp:")
    if phone.startswith("client:"):
        phone = phone.removeprefix("client:")
    return phone.replace(" ", "")


def _get_clinical_conversation(db: Session, clinic: Clinic, conversation_id: int) -> ClinicConversation:
    conversation = db.scalars(select(ClinicConversation).where(
        ClinicConversation.id == conversation_id,
        ClinicConversation.clinic_id == clinic.id,
    )).first()
    if conversation is None:
        raise NotFoundError("Clinical conversation not found")
    return conversation

def resolve_appointment_doctor(
    db: Session,
    clinic: Clinic,
    *,
    physician_name: str | None = None,
    department: str | None = None,
) -> Doctor | None:
    """Resolve an appointment to a login-linked clinician, deterministically."""
    linked_doctors = list(
        db.scalars(
            select(Doctor)
            .where(Doctor.clinic_id == clinic.id, Doctor.user_id.is_not(None), Doctor.is_active.is_(True))
            .order_by(Doctor.id)
        )
    )
    if not linked_doctors:
        return None
    if physician_name:
        normalized_name = physician_name.strip().casefold()
        for doctor in linked_doctors:
            doctor_name = doctor.full_name.strip().casefold()
            if normalized_name == doctor_name or normalized_name in doctor_name or doctor_name in normalized_name:
                return doctor
        # Açıkça adı verilen ama sisteme bağlı olmayan hekimi başka bir hekime
        # sessizce atama; operatörün eşleştirmesi için atamasız bırak.
        return None
    if department:
        normalized_department = department.strip().casefold()
        for doctor in linked_doctors:
            if doctor.specialty.strip().casefold() == normalized_department:
                return doctor
    return linked_doctors[0]

def create_clinical_appointment_from_conversation(
    db: Session,
    clinic: Clinic,
    conversation_id: int,
    department: str,
    starts_at: datetime | None,
    duration_minutes: int = 30,
    visit_reason: str | None = None,
    notes: str | None = None,
) -> ClinicalAppointment:
    conversation = _get_clinical_conversation(db, clinic, conversation_id)
    assigned_doctor = resolve_appointment_doctor(db, clinic, department=department)
    appointment = ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=conversation.patient_id,
        conversation_id=conversation.id,
        assigned_doctor_id=assigned_doctor.id if assigned_doctor else None,
        department=department.strip() or "Muayene",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=duration_minutes) if starts_at else None,
        duration_minutes=duration_minutes,
        visit_reason=visit_reason,
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


def upcoming_clinical_appointments(
    db: Session,
    clinic: Clinic,
    within_minutes: int = 120,
    *,
    doctor_id: int | None = None,
) -> list[ClinicalAppointment]:
    now = datetime.now(timezone.utc)
    query = (
        select(ClinicalAppointment)
        .options(
            selectinload(ClinicalAppointment.procedures),
            selectinload(ClinicalAppointment.assigned_doctor),
        )
        .where(
            ClinicalAppointment.clinic_id == clinic.id,
            ClinicalAppointment.status == ClinicalAppointmentStatus.CONFIRMED,
            ClinicalAppointment.starts_at.is_not(None),
            ClinicalAppointment.starts_at >= now,
            ClinicalAppointment.starts_at <= now + timedelta(minutes=within_minutes),
        )
    )
    if doctor_id is not None:
        query = query.where(ClinicalAppointment.assigned_doctor_id == doctor_id)
    return list(
        db.scalars(
            query.order_by(ClinicalAppointment.starts_at.asc())
        )
    )


def recent_clinical_appointments(
    db: Session,
    clinic: Clinic,
    limit: int = 50,
    *,
    doctor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[ClinicalAppointment]:
    """Operatör paneli için kliniğin son randevuları (tüm statüler), en yeni önce."""
    query = (
        select(ClinicalAppointment)
        .options(
            selectinload(ClinicalAppointment.procedures),
            selectinload(ClinicalAppointment.assigned_doctor),
        )
        .where(ClinicalAppointment.clinic_id == clinic.id)
    )
    if doctor_id is not None:
        query = query.where(ClinicalAppointment.assigned_doctor_id == doctor_id)
    if date_from is not None:
        query = query.where(ClinicalAppointment.starts_at >= date_from)
    if date_to is not None:
        query = query.where(ClinicalAppointment.starts_at < date_to)
    return list(
        db.scalars(
            query.order_by(ClinicalAppointment.starts_at.asc().nullslast(), ClinicalAppointment.created_at.desc()).limit(limit)
        )
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _appointment_end(appointment: ClinicalAppointment) -> datetime | None:
    if appointment.ends_at is not None:
        return _aware(appointment.ends_at)
    if appointment.starts_at is None:
        return None
    return _aware(appointment.starts_at) + timedelta(minutes=appointment.duration_minutes or 30)


def ensure_doctor_schedule_available(
    db: Session,
    appointment: ClinicalAppointment,
    *,
    starts_at: datetime | None = None,
    duration_minutes: int | None = None,
) -> None:
    start = starts_at if starts_at is not None else appointment.starts_at
    if start is None:
        raise ValidationError("Onaylanan randevu için tarih ve saat zorunludur")
    if appointment.assigned_doctor_id is None:
        raise ValidationError("Randevu aktif bir hekime atanmalıdır")
    start = _aware(start)
    duration = duration_minutes or appointment.duration_minutes or 30
    end = start + timedelta(minutes=duration)
    candidates = db.scalars(
        select(ClinicalAppointment).where(
            ClinicalAppointment.clinic_id == appointment.clinic_id,
            ClinicalAppointment.assigned_doctor_id == appointment.assigned_doctor_id,
            ClinicalAppointment.status == ClinicalAppointmentStatus.CONFIRMED,
            ClinicalAppointment.id != appointment.id,
            ClinicalAppointment.starts_at.is_not(None),
        )
    ).all()
    for existing in candidates:
        existing_start = _aware(existing.starts_at) if existing.starts_at else None
        existing_end = _appointment_end(existing)
        if existing_start is not None and existing_end is not None and start < existing_end and end > existing_start:
            raise ConflictError(
                "Hekimin bu saat aralığında başka bir onaylı randevusu var",
                details={
                    "conflicting_appointment_id": existing.id,
                    "starts_at": existing_start.isoformat(),
                    "ends_at": existing_end.isoformat(),
                },
            )


def set_clinical_appointment_status(
    db: Session,
    clinic: Clinic,
    appointment_id: int,
    status_value: str,
    *,
    doctor_id: int | None = None,
) -> ClinicalAppointment:
    """Operatör randevu durumunu günceller (pending → confirmed/cancelled)."""
    query = select(ClinicalAppointment).where(
        ClinicalAppointment.id == appointment_id,
        ClinicalAppointment.clinic_id == clinic.id,
    )
    if doctor_id is not None:
        query = query.where(ClinicalAppointment.assigned_doctor_id == doctor_id)
    appointment = db.scalars(query).first()
    if appointment is None:
        raise NotFoundError("Appointment not found")
    next_status = ClinicalAppointmentStatus(status_value)
    if next_status == ClinicalAppointmentStatus.CONFIRMED:
        ensure_doctor_schedule_available(db, appointment)
        appointment.ends_at = _aware(appointment.starts_at) + timedelta(minutes=appointment.duration_minutes or 30)
    appointment.status = next_status
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def create_manual_clinical_appointment(
    db: Session,
    clinic: Clinic,
    *,
    full_name: str | None,
    phone: str,
    department: str,
    starts_at: datetime | None,
    duration_minutes: int,
    visit_reason: str | None,
    physician_name: str | None,
    branch_name: str | None,
    notes: str | None,
) -> ClinicalAppointment:
    """Operatörün panelden (sohbet olmadan) açtığı randevu.

    Mevcut hasta telefon numarasından bulunur, yoksa minimal kayıt açılır.
    Slot panosundan tıklanan dilim bilgisi metadata_json'a düşer.
    """
    normalized_phone = _normalize_phone(phone)
    patient = db.scalars(
        select(ClinicPatient).where(
            ClinicPatient.clinic_id == clinic.id, ClinicPatient.phone == normalized_phone
        )
    ).first()
    if patient is None:
        patient = ClinicPatient(
            clinic_id=clinic.id,
            full_name=full_name,
            phone=normalized_phone,
            language=clinic.default_language or "tr",
            source=ClinicChannel.PHONE,
            external_ref=normalized_phone,
            metadata_json={},
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
    elif full_name and not patient.full_name:
        patient.full_name = full_name
        db.add(patient)
        db.commit()
        db.refresh(patient)

    metadata: dict = {"created_by": "operator_panel"}
    if physician_name:
        metadata["physician_name"] = physician_name
    if branch_name:
        metadata["branch_name"] = branch_name

    assigned_doctor = resolve_appointment_doctor(
        db,
        clinic,
        physician_name=physician_name,
        department=department,
    )

    appointment = ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=None,
        assigned_doctor_id=assigned_doctor.id if assigned_doctor else None,
        department=department,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=duration_minutes) if starts_at else None,
        duration_minutes=duration_minutes,
        visit_reason=visit_reason,
        status=ClinicalAppointmentStatus.PENDING,
        notes=notes,
        metadata_json=metadata,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def update_appointment_clinical_details(
    db: Session,
    clinic: Clinic,
    appointment_id: int,
    *,
    doctor_id: int | None,
    starts_at: datetime | None,
    duration_minutes: int | None,
    visit_reason: str | None,
    notes: str | None,
    procedures: list[dict] | None,
    fields_set: set[str],
) -> ClinicalAppointment:
    query = (
        select(ClinicalAppointment)
        .options(selectinload(ClinicalAppointment.procedures), selectinload(ClinicalAppointment.assigned_doctor))
        .where(ClinicalAppointment.id == appointment_id, ClinicalAppointment.clinic_id == clinic.id)
    )
    if doctor_id is not None:
        query = query.where(ClinicalAppointment.assigned_doctor_id == doctor_id)
    appointment = db.scalars(query).first()
    if appointment is None:
        raise NotFoundError("Appointment not found")

    next_start = starts_at if "starts_at" in fields_set else appointment.starts_at
    next_duration = duration_minutes if duration_minutes is not None else appointment.duration_minutes
    if appointment.status == ClinicalAppointmentStatus.CONFIRMED and (
        "starts_at" in fields_set or "duration_minutes" in fields_set
    ):
        ensure_doctor_schedule_available(
            db,
            appointment,
            starts_at=next_start,
            duration_minutes=next_duration,
        )

    if "starts_at" in fields_set:
        appointment.starts_at = starts_at
    if "duration_minutes" in fields_set and duration_minutes is not None:
        appointment.duration_minutes = duration_minutes
    if "visit_reason" in fields_set:
        appointment.visit_reason = visit_reason.strip() if visit_reason else None
    if "notes" in fields_set:
        appointment.notes = notes.strip() if notes else None
    appointment.ends_at = (
        _aware(appointment.starts_at) + timedelta(minutes=appointment.duration_minutes)
        if appointment.starts_at
        else None
    )

    if procedures is not None:
        by_id = {item.id: item for item in appointment.procedures}
        now = datetime.now(timezone.utc)
        for index, payload in enumerate(procedures):
            procedure_id = payload.get("id")
            if procedure_id is not None:
                procedure = by_id.get(procedure_id)
                if procedure is None:
                    raise ValidationError("İşlem bu randevuya ait değil")
            else:
                procedure = ClinicalAppointmentProcedure(
                    clinic_id=clinic.id,
                    appointment_id=appointment.id,
                    name=payload["name"].strip(),
                )
            procedure.name = payload["name"].strip()
            procedure.code = payload.get("code") or None
            procedure.tooth = payload.get("tooth") or None
            procedure.notes = payload.get("notes") or None
            procedure.sort_order = payload.get("sort_order", index)
            next_procedure_status = ClinicalProcedureStatus(payload.get("status", "planned"))
            if next_procedure_status == ClinicalProcedureStatus.IN_PROGRESS and procedure.started_at is None:
                procedure.started_at = now
            if next_procedure_status == ClinicalProcedureStatus.COMPLETED:
                procedure.started_at = procedure.started_at or now
                procedure.completed_at = now
                procedure.performed_by_doctor_id = doctor_id or appointment.assigned_doctor_id
            elif next_procedure_status != ClinicalProcedureStatus.COMPLETED:
                procedure.completed_at = None
            procedure.status = next_procedure_status
            db.add(procedure)

    db.add(appointment)
    db.commit()
    return db.scalars(
        select(ClinicalAppointment)
        .options(selectinload(ClinicalAppointment.procedures), selectinload(ClinicalAppointment.assigned_doctor))
        .where(ClinicalAppointment.id == appointment.id)
    ).one()

