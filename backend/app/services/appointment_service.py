from __future__ import annotations

from datetime import datetime
import re
import secrets

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentSlot, AuditResultStatus, RoleName, User
from app.services.audit_service import log_action


def normalize_department(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    mapping = {
        "onboarding": "Onboarding Desk",
        "kurulum": "Onboarding Desk",
        "başlangıç": "Onboarding Desk",
        "support": "Technical Support",
        "teknik": "Technical Support",
        "billing": "Billing Operations",
        "fatura": "Billing Operations",
        "compliance": "Compliance Advisory",
        "uyum": "Compliance Advisory",
    }
    for key, department in mapping.items():
        if key in text:
            return department
    if value in mapping.values():
        return value
    return None


def format_slot_label(slot: AppointmentSlot) -> str:
    return f"{slot.department} | {slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')} | {slot.location}"


def check_available_slots(
    db: Session, department: str | None = None, preferred_date: str | None = None, limit: int = 3
) -> list[AppointmentSlot]:
    query: Select[tuple[AppointmentSlot]] = select(AppointmentSlot).where(AppointmentSlot.is_booked.is_(False))
    normalized_department = normalize_department(department)
    if normalized_department:
        query = query.where(AppointmentSlot.department == normalized_department)
    if preferred_date:
        parsed_date = None
        try:
            parsed_date = datetime.fromisoformat(preferred_date).date()
        except ValueError:
            pass
        if parsed_date is not None:
            query = query.where(AppointmentSlot.start_time >= datetime.combine(parsed_date, datetime.min.time()))
    query = query.order_by(AppointmentSlot.start_time.asc()).limit(limit)
    return list(db.scalars(query))


def create_appointment(
    db: Session,
    *,
    acting_user: User,
    slot_id: int,
    purpose: str,
    contact_phone: str,
    language: str,
    notes: str | None = None,
    target_user_id: int | None = None,
) -> Appointment:
    target_user_id = target_user_id or acting_user.id
    if acting_user.role.name == RoleName.CUSTOMER and target_user_id != acting_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers can only create their own request")

    slot = db.get(AppointmentSlot, slot_id)
    if slot is None or slot.is_booked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected slot is not available")

    cleaned_phone = re.sub(r"[^\d+]", "", contact_phone)
    if len(cleaned_phone) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number is too short")

    appointment = Appointment(
        user_id=target_user_id,
        slot_id=slot.id,
        department=slot.department,
        purpose=purpose.strip(),
        contact_phone=contact_phone.strip(),
        notes=notes.strip() if notes else None,
        language=language,
        confirmation_code=f"CV-{secrets.token_hex(3).upper()}",
        created_by_user_id=acting_user.id,
    )
    slot.is_booked = True
    db.add(appointment)
    db.add(slot)
    db.commit()
    db.refresh(appointment)

    log_action(
        db,
        user_id=acting_user.id,
        action_type="appointment.created",
        explanation="Appointment created successfully",
        result_status=AuditResultStatus.SUCCESS,
        tool_name="create_appointment",
        details={
            "appointment_id": appointment.id,
            "confirmation_code": appointment.confirmation_code,
            "target_user_id": target_user_id,
            "slot_id": slot.id,
        },
    )
    return appointment


def list_appointments(db: Session, current_user: User) -> list[Appointment]:
    query = select(Appointment).join(AppointmentSlot, Appointment.slot_id == AppointmentSlot.id).order_by(Appointment.created_at.desc())
    if current_user.role.name == RoleName.CUSTOMER:
        query = query.where(Appointment.user_id == current_user.id)
    return list(db.scalars(query))


def appointment_payload(appointment: Appointment) -> dict:
    return {
        "id": appointment.id,
        "confirmation_code": appointment.confirmation_code,
        "department": appointment.department,
        "purpose": appointment.purpose,
        "contact_phone": appointment.contact_phone,
        "notes": appointment.notes,
        "language": appointment.language,
        "status": appointment.status.value,
        "scheduled_at": appointment.slot.start_time,
        "location": appointment.slot.location,
        "created_at": appointment.created_at,
        "user_name": appointment.user.full_name if appointment.user else None,
        "user_id": appointment.user_id,
    }
