import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class AppointmentType(str, Enum):
    WALK_IN = "walk_in"
    SCHEDULED = "scheduled"
    FOLLOW_UP = "follow_up"
    EMERGENCY = "emergency"
    TELEMEDICINE = "telemedicine"


class CancellationReason(str, Enum):
    PATIENT_REQUEST = "patient_request"
    DOCTOR_UNAVAILABLE = "doctor_unavailable"
    CLINIC_EMERGENCY = "clinic_emergency"
    OTHER = "other"


class Appointment(BaseModel):
    __tablename__ = "appointments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False, index=True
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH:MM:SS
    end_time: Mapped[str | None] = mapped_column(String(8))
    appointment_type: Mapped[AppointmentType] = mapped_column(
        SAEnum(AppointmentType), default=AppointmentType.SCHEDULED
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus), default=AppointmentStatus.SCHEDULED, index=True
    )
    token_number: Mapped[int | None] = mapped_column(Integer)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consultation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consultation_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[CancellationReason | None] = mapped_column(SAEnum(CancellationReason))
    cancellation_notes: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Rescheduling
    original_appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship("Patient", back_populates="appointments")
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="appointments")
    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="appointments")
    encounter: Mapped["Encounter | None"] = relationship("Encounter", back_populates="appointment", uselist=False)
