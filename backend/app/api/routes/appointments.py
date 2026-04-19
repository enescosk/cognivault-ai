from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.schemas.appointment import AppointmentCreateRequest, AppointmentResponse, AppointmentSlotResponse
from app.services.appointment_service import appointment_payload, check_available_slots, create_appointment, list_appointments


router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentResponse])
def get_appointments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[AppointmentResponse]:
    appointments = list_appointments(db, current_user)
    return [AppointmentResponse(**appointment_payload(appointment)) for appointment in appointments]


@router.get("/slots", response_model=list[AppointmentSlotResponse])
def get_slots(
    department: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AppointmentSlotResponse]:
    slots = check_available_slots(db, department=department)
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
