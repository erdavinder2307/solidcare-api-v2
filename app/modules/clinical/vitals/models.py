import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class Vital(BaseModel):
    __tablename__ = "vitals"

    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Vitals
    systolic_bp: Mapped[int | None] = mapped_column(Integer)       # mmHg
    diastolic_bp: Mapped[int | None] = mapped_column(Integer)      # mmHg
    pulse_rate: Mapped[int | None] = mapped_column(Integer)        # bpm
    respiratory_rate: Mapped[int | None] = mapped_column(Integer)  # breaths/min
    temperature: Mapped[float | None] = mapped_column(Float)       # Celsius
    temperature_unit: Mapped[str] = mapped_column(String(1), default="C")
    spo2: Mapped[int | None] = mapped_column(Integer)              # %
    weight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    blood_glucose: Mapped[float | None] = mapped_column(Float)     # mg/dL
    blood_glucose_type: Mapped[str | None] = mapped_column(String(20))  # fasting/random/pp
    pain_scale: Mapped[int | None] = mapped_column(Integer)        # 0-10
    notes: Mapped[str | None] = mapped_column()

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="vitals")

    @property
    def calculated_bmi(self) -> float | None:
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            height_m = self.height_cm / 100
            return round(self.weight_kg / (height_m ** 2), 1)
        return None
