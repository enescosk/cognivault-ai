from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    purpose: str = Field(min_length=1, max_length=500)
    contact_phone: str = Field(min_length=7, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)
    target_user_id: int | None = None
    language: str = Field(default="en", max_length=10)


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
