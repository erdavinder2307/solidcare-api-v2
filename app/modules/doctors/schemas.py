import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.doctors.models import DayOfWeek, DoctorStatus


class DoctorCreate(BaseModel):
    user_id: uuid.UUID
    registration_number: str | None = None
    registration_council: str | None = None
    qualifications: list[str] | None = None
    specializations: list[str] | None = None
    sub_specializations: list[str] | None = None
    years_of_experience: int | None = None
    consultation_fee: float | None = None
    follow_up_fee: float | None = None
    bio: str | None = None
    languages: list[str] | None = None


class DoctorUpdate(BaseModel):
    registration_number: str | None = None
    qualifications: list[str] | None = None
    specializations: list[str] | None = None
    years_of_experience: int | None = None
    consultation_fee: float | None = None
    follow_up_fee: float | None = None
    bio: str | None = None
    status: DoctorStatus | None = None
    languages: list[str] | None = None


class DoctorResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    registration_number: str | None
    qualifications: list[str] | None
    specializations: list[str] | None
    years_of_experience: int | None
    consultation_fee: float | None
    follow_up_fee: float | None
    bio: str | None
    status: DoctorStatus
    languages: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleCreate(BaseModel):
    clinic_id: uuid.UUID
    day_of_week: DayOfWeek
    start_time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    slot_duration_minutes: int = Field(default=15, ge=5, le=120)
    max_appointments: int | None = None


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    day_of_week: DayOfWeek
    start_time: str
    end_time: str
    slot_duration_minutes: int
    max_appointments: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class ClinicAssignmentCreate(BaseModel):
    clinic_id: uuid.UUID
    is_primary: bool = False
    consultation_fee_override: float | None = None
