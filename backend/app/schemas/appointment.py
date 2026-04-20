from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AppointmentSlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department: str
    start_time: datetime
    end_time: datetime
    location: str
    is_booked: bool


class AppointmentCreateRequest(BaseModel):
    slot_id: int
    purpose: str
    contact_phone: str
    notes: str | None = None
    target_user_id: int | None = None
    language: str = "en"


class AppointmentResponse(BaseModel):
    id: int
    confirmation_code: str
    department: str
    purpose: str
    contact_phone: str
    notes: str | None = None
    language: str
    status: str
    scheduled_at: datetime
    location: str
    created_at: datetime
    user_name: str | None = None
    user_id: int | None = None


class AppointmentConfirmationCard(BaseModel):
    type: str = "appointment_confirmation"
    confirmation_code: str
    department: str
    scheduled_at: datetime
    location: str
    contact_phone: str
    status: str
