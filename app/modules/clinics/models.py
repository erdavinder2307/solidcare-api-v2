import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class ClinicType(str, Enum):
    GENERAL = "general"
    SPECIALTY = "specialty"
    MULTISPECIALTY = "multispecialty"
    DIAGNOSTIC = "diagnostic"
    HOSPITAL = "hospital"


class Clinic(BaseModel):
    __tablename__ = "clinics"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    clinic_type: Mapped[ClinicType] = mapped_column(
        SAEnum(ClinicType), default=ClinicType.GENERAL
    )
    registration_number: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    gstin: Mapped[str | None] = mapped_column(String(20))
    logo_url: Mapped[str | None] = mapped_column(Text)
    letterhead_footer: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="clinics")
    doctor_assignments: Mapped[list["DoctorClinicAssignment"]] = relationship(
        "DoctorClinicAssignment", back_populates="clinic"
    )
    appointments: Mapped[list["Appointment"]] = relationship("Appointment", back_populates="clinic")
