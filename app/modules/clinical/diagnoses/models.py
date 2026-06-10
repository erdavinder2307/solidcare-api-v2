import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, Text, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class DiagnosisType(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DIFFERENTIAL = "differential"
    PROVISIONAL = "provisional"


class DiagnosisStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    CHRONIC = "chronic"
    RULED_OUT = "ruled_out"


class Diagnosis(BaseModel):
    __tablename__ = "diagnoses"

    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    icd10_code: Mapped[str | None] = mapped_column(String(20), index=True)
    icd10_description: Mapped[str | None] = mapped_column(String(500))
    custom_description: Mapped[str | None] = mapped_column(Text)
    diagnosis_type: Mapped[DiagnosisType] = mapped_column(
        SAEnum(DiagnosisType), default=DiagnosisType.PRIMARY
    )
    status: Mapped[DiagnosisStatus] = mapped_column(
        SAEnum(DiagnosisStatus), default=DiagnosisStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_chronic: Mapped[bool] = mapped_column(Boolean, default=False)

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="diagnoses")


class ICD10Code(BaseModel):
    """Master ICD-10 code reference table."""

    __tablename__ = "icd10_codes"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(200))
    chapter: Mapped[str | None] = mapped_column(String(200))
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True)
