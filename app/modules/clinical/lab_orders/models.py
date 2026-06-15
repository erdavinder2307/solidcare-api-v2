import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class LabOrderStatus(str, Enum):
    ORDERED = "ordered"
    COLLECTED = "collected"
    PROCESSING = "processing"
    RESULTED = "resulted"
    CANCELLED = "cancelled"


class LabOrder(BaseModel):
    __tablename__ = "lab_orders"

    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    ordered_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False
    )
    lab_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LabOrderStatus] = mapped_column(
        SAEnum(LabOrderStatus), default=LabOrderStatus.ORDERED
    )
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="lab_orders")
    items: Mapped[list["LabOrderItem"]] = relationship("LabOrderItem", back_populates="lab_order")
    results: Mapped[list["LabResult"]] = relationship("LabResult", back_populates="lab_order")


class LabOrderItem(BaseModel):
    __tablename__ = "lab_order_items"

    lab_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_orders.id"), nullable=False, index=True
    )
    test_name: Mapped[str] = mapped_column(String(200), nullable=False)
    test_code: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    lab_order: Mapped["LabOrder"] = relationship("LabOrder", back_populates="items")


class LabResult(BaseModel):
    __tablename__ = "lab_results"

    lab_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_orders.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    test_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_range: Mapped[str | None] = mapped_column(String(100))
    is_abnormal: Mapped[bool | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    result_pdf_path: Mapped[str | None] = mapped_column(Text)

    lab_order: Mapped["LabOrder"] = relationship("LabOrder", back_populates="results")
