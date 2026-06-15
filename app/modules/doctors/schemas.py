import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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


class DoctorRegisterCreate(BaseModel):
    """Create a user account, doctor profile, clinic assignment, and default schedule."""

    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    clinic_id: uuid.UUID
    registration_number: str | None = None
    registration_council: str | None = None
    qualifications: list[str] | None = None
    specializations: list[str] | None = None
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
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_doctor(cls, doctor) -> "DoctorResponse":
        user = getattr(doctor, "user", None)
        return cls(
            id=doctor.id,
            organization_id=doctor.organization_id,
            user_id=doctor.user_id,
            registration_number=doctor.registration_number,
            qualifications=doctor.qualifications,
            specializations=doctor.specializations,
            years_of_experience=doctor.years_of_experience,
            consultation_fee=doctor.consultation_fee,
            follow_up_fee=doctor.follow_up_fee,
            bio=doctor.bio,
            status=doctor.status,
            languages=doctor.languages,
            created_at=doctor.created_at,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            email=user.email if user else None,
        )


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
