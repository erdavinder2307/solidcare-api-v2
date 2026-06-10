import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, Float, Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class EncounterStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EncounterType(str, Enum):
    OPD = "opd"
    IPD = "ipd"
    EMERGENCY = "emergency"
    TELEMEDICINE = "telemedicine"


class Encounter(BaseModel):
    __tablename__ = "encounters"

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
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    encounter_type: Mapped[EncounterType] = mapped_column(
        SAEnum(EncounterType), default=EncounterType.OPD
    )
    status: Mapped[EncounterStatus] = mapped_column(
        SAEnum(EncounterStatus), default=EncounterStatus.IN_PROGRESS
    )
    encounter_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # SOAP Notes
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    history_of_present_illness: Mapped[str | None] = mapped_column(Text)
    past_medical_history: Mapped[str | None] = mapped_column(Text)
    past_surgical_history: Mapped[str | None] = mapped_column(Text)
    family_history: Mapped[str | None] = mapped_column(Text)
    social_history: Mapped[str | None] = mapped_column(Text)
    review_of_systems: Mapped[str | None] = mapped_column(Text)
    # Objective
    general_examination: Mapped[str | None] = mapped_column(Text)
    systemic_examination: Mapped[str | None] = mapped_column(Text)
    # Assessment
    clinical_impression: Mapped[str | None] = mapped_column(Text)
    # Plan
    treatment_plan: Mapped[str | None] = mapped_column(Text)
    follow_up_instructions: Mapped[str | None] = mapped_column(Text)
    follow_up_days: Mapped[int | None] = mapped_column()
    referral_to: Mapped[str | None] = mapped_column(String(200))
    referral_notes: Mapped[str | None] = mapped_column(Text)
    # PDF
    summary_pdf_path: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    appointment: Mapped["Appointment | None"] = relationship("Appointment", back_populates="encounter")
    vitals: Mapped[list["Vital"]] = relationship("Vital", back_populates="encounter")
    diagnoses: Mapped[list["Diagnosis"]] = relationship("Diagnosis", back_populates="encounter")
    prescriptions: Mapped[list["Prescription"]] = relationship("Prescription", back_populates="encounter")
    lab_orders: Mapped[list["LabOrder"]] = relationship("LabOrder", back_populates="encounter")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="encounter", uselist=False)
