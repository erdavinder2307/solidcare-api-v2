import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class BloodGroup(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "Unknown"


class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    OTHER = "other"


class DocumentType(str, Enum):
    AADHAAR = "aadhaar"
    PAN = "pan"
    PASSPORT = "passport"
    DRIVING_LICENSE = "driving_license"
    VOTER_ID = "voter_id"
    OTHER = "other"


class ConsentType(str, Enum):
    TREATMENT = "treatment"
    DATA_SHARING = "data_sharing"
    MARKETING = "marketing"
    ABDM = "abdm"
    TELEMEDICINE = "telemedicine"


class Patient(BaseModel):
    __tablename__ = "patients"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Unique patient identifier within the organization
    uhid: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    blood_group: Mapped[BloodGroup | None] = mapped_column(SAEnum(BloodGroup))
    marital_status: Mapped[MaritalStatus | None] = mapped_column(SAEnum(MaritalStatus))
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(50), default="India")
    occupation: Mapped[str | None] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(50))
    religion: Mapped[str | None] = mapped_column(String(50))
    known_allergies: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    known_conditions: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # ABDM integration
    abha_number: Mapped[str | None] = mapped_column(String(20), index=True)
    abha_address: Mapped[str | None] = mapped_column(String(100))
    # Emergency contact
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(50))
    # Insurance
    insurance_provider: Mapped[str | None] = mapped_column(String(100))
    insurance_policy_number: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Deduplication flag
    is_merged: Mapped[bool] = mapped_column(Boolean, default=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    appointments: Mapped[list["Appointment"]] = relationship("Appointment", back_populates="patient")
    documents: Mapped[list["PatientDocument"]] = relationship("PatientDocument", back_populates="patient")
    consents: Mapped[list["PatientConsent"]] = relationship("PatientConsent", back_populates="patient")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PatientDocument(BaseModel):
    __tablename__ = "patient_documents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="documents")


class PatientConsent(BaseModel):
    __tablename__ = "patient_consents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(SAEnum(ConsentType), nullable=False)
    consented: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consented_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    notes: Mapped[str | None] = mapped_column(Text)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="consents")
