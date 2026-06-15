from enum import Enum

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models.base import BaseModel


class DosageForm(str, Enum):
    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    INJECTION = "injection"
    OINTMENT = "ointment"
    CREAM = "cream"
    DROP = "drop"
    INHALER = "inhaler"
    PATCH = "patch"
    SUPPOSITORY = "suppository"
    POWDER = "powder"
    OTHER = "other"


class Medicine(BaseModel):
    __tablename__ = "medicines"

    generic_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    drug_class: Mapped[str | None] = mapped_column(String(100))
    dosage_form: Mapped[DosageForm] = mapped_column(SAEnum(DosageForm), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(50))
    mrp: Mapped[float | None] = mapped_column(Float)
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_class: Mapped[str | None] = mapped_column(String(10))  # H, H1, X etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    contraindications: Mapped[str | None] = mapped_column(Text)
    side_effects: Mapped[str | None] = mapped_column(Text)
    drug_interactions: Mapped[str | None] = mapped_column(Text)
    storage_instructions: Mapped[str | None] = mapped_column(Text)
