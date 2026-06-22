from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentRescheduleRequest,
    AppointmentResponse,
    AppointmentSlotResponse,
)
from app.services.appointment_service import (
    appointment_payload,
    cancel_appointment,
    check_available_slots,
    create_appointment,
    list_appointments,
    reschedule_appointment,
)


router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentResponse])
def get_appointments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[AppointmentResponse]:
    appointments = list_appointments(db, current_user)
    return [AppointmentResponse(**appointment_payload(appointment)) for appointment in appointments]


@router.get("/slots", response_model=list[AppointmentSlotResponse])
def get_slots(
    department: str | None = None,
    preferred_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AppointmentSlotResponse]:
    slots = check_available_slots(db, department=department, preferred_date=preferred_date, limit=8)
    return [AppointmentSlotResponse.model_validate(slot) for slot in slots]


@router.post("", response_model=AppointmentResponse)
def post_appointment(
    payload: AppointmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AppointmentResponse:
    appointment = create_appointment(
        db,
        acting_user=current_user,
        slot_id=payload.slot_id,
        purpose=payload.purpose,
        contact_phone=payload.contact_phone,
        notes=payload.notes,
        language=payload.language,
        target_user_id=payload.target_user_id,
    )
    return AppointmentResponse(**appointment_payload(appointment))


@router.patch("/{appointment_id}/cancel", response_model=AppointmentResponse)
def patch_cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AppointmentResponse:
    appointment = cancel_appointment(db, appointment_id=appointment_id, current_user=current_user)
    return AppointmentResponse(**appointment_payload(appointment))


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentResponse)
def patch_reschedule_appointment(
    appointment_id: int,
    payload: AppointmentRescheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AppointmentResponse:
    appointment = reschedule_appointment(
        db,
        appointment_id=appointment_id,
        slot_id=payload.slot_id,
        current_user=current_user,
    )
    return AppointmentResponse(**appointment_payload(appointment))
