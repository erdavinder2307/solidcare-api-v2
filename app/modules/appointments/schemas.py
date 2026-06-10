import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.appointments.models import AppointmentStatus, AppointmentType, CancellationReason


class AppointmentCreate(BaseModel):
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    appointment_date: date
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    appointment_type: AppointmentType = AppointmentType.SCHEDULED
    chief_complaint: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    appointment_date: date | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    chief_complaint: str | None = None
    notes: str | None = None


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus
    cancellation_reason: CancellationReason | None = None
    cancellation_notes: str | None = None


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    appointment_date: date
    start_time: str
    end_time: str | None
    appointment_type: AppointmentType
    status: AppointmentStatus
    token_number: int | None
    chief_complaint: str | None
    notes: str | None
    checked_in_at: datetime | None
    consultation_started_at: datetime | None
    consultation_ended_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AppointmentListItem(BaseModel):
    id: uuid.UUID
    appointment_date: date
    start_time: str
    appointment_type: AppointmentType
    status: AppointmentStatus
    token_number: int | None
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    chief_complaint: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
