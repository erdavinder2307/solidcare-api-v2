import uuid
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class FrequencyCode(str, Enum):
    OD = "OD"       # Once daily
    BD = "BD"       # Twice daily
    TDS = "TDS"     # Three times daily
    QID = "QID"     # Four times daily
    SOS = "SOS"     # As needed
    HS = "HS"       # At bedtime
    STAT = "STAT"   # Immediately
    OW = "OW"       # Once weekly
    CUSTOM = "CUSTOM"


class MealRelation(str, Enum):
    BEFORE_FOOD = "before_food"
    AFTER_FOOD = "after_food"
    WITH_FOOD = "with_food"
    EMPTY_STOMACH = "empty_stomach"
    ANY_TIME = "any_time"


class PrescriptionStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    DISPENSED = "dispensed"
    CANCELLED = "cancelled"


class Prescription(BaseModel):
    __tablename__ = "prescriptions"

    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=False
    )
    status: Mapped[PrescriptionStatus] = mapped_column(
        SAEnum(PrescriptionStatus), default=PrescriptionStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text)
    diagnosis_summary: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="prescriptions")
    items: Mapped[list["PrescriptionItem"]] = relationship(
        "PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan"
    )


class PrescriptionItem(BaseModel):
    __tablename__ = "prescription_items"

    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id"), nullable=False, index=True
    )
    medicine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=True
    )
    medicine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[FrequencyCode] = mapped_column(SAEnum(FrequencyCode))
    frequency_custom: Mapped[str | None] = mapped_column(String(100))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[str | None] = mapped_column(String(50))
    meal_relation: Mapped[MealRelation] = mapped_column(
        SAEnum(MealRelation), default=MealRelation.AFTER_FOOD
    )
    instructions: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    prescription: Mapped["Prescription"] = relationship("Prescription", back_populates="items")
    medicine: Mapped["Medicine | None"] = relationship("Medicine")
