import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Time, Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class DoctorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_LEAVE = "on_leave"


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class Doctor(BaseModel):
    __tablename__ = "doctors"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    registration_number: Mapped[str | None] = mapped_column(String(50), index=True)
    registration_council: Mapped[str | None] = mapped_column(String(100))
    qualifications: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    specializations: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    sub_specializations: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    years_of_experience: Mapped[int | None] = mapped_column(Integer)
    consultation_fee: Mapped[float | None] = mapped_column()
    follow_up_fee: Mapped[float | None] = mapped_column()
    bio: Mapped[str | None] = mapped_column(Text)
    signature_blob_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DoctorStatus] = mapped_column(
        SAEnum(DoctorStatus), default=DoctorStatus.ACTIVE
    )
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    user: Mapped["User"] = relationship("User")
    clinic_assignments: Mapped[list["DoctorClinicAssignment"]] = relationship(
        "DoctorClinicAssignment", back_populates="doctor"
    )
    schedules: Mapped[list["DoctorSchedule"]] = relationship(
        "DoctorSchedule", back_populates="doctor"
    )
    appointments: Mapped[list["Appointment"]] = relationship("Appointment", back_populates="doctor")


class DoctorClinicAssignment(BaseModel):
    __tablename__ = "doctor_clinic_assignments"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    consultation_fee_override: Mapped[float | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="clinic_assignments")
    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="doctor_assignments")


class DoctorSchedule(BaseModel):
    __tablename__ = "doctor_schedules"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False, index=True
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(SAEnum(DayOfWeek), nullable=False)
    start_time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH:MM:SS
    end_time: Mapped[str] = mapped_column(String(8), nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    max_appointments: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="schedules")
