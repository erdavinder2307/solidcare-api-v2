"""
Notification event handlers — wired to the event bus.
"""

import logging
import uuid
from dataclasses import dataclass

from app.core.events.bus import DomainEvent, event_bus

logger = logging.getLogger(__name__)


@dataclass
class AppointmentBooked(DomainEvent):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    appointment_date: str
    appointment_time: str
    patient_phone: str
    patient_email: str | None


@dataclass
class AppointmentCancelled(DomainEvent):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    patient_phone: str
    reason: str | None


@dataclass
class AppointmentReminder(DomainEvent):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    patient_phone: str
    patient_email: str | None
    hours_before: int


@dataclass
class PrescriptionGenerated(DomainEvent):
    prescription_id: uuid.UUID
    patient_id: uuid.UUID
    patient_phone: str
    patient_email: str | None
    pdf_url: str


@dataclass
class InvoiceGenerated(DomainEvent):
    invoice_id: uuid.UUID
    patient_id: uuid.UUID
    patient_phone: str
    patient_email: str | None
    amount: float


@event_bus.subscribe(AppointmentBooked)
async def on_appointment_booked(event: AppointmentBooked) -> None:
    logger.info(
        "NOTIFICATION: Appointment booked – sending confirmation to patient %s",
        event.patient_id,
    )
    # Celery task will be dispatched here in Phase 8


@event_bus.subscribe(AppointmentCancelled)
async def on_appointment_cancelled(event: AppointmentCancelled) -> None:
    logger.info("NOTIFICATION: Appointment %s cancelled", event.appointment_id)


@event_bus.subscribe(PrescriptionGenerated)
async def on_prescription_generated(event: PrescriptionGenerated) -> None:
    logger.info("NOTIFICATION: Prescription %s ready", event.prescription_id)


@event_bus.subscribe(InvoiceGenerated)
async def on_invoice_generated(event: InvoiceGenerated) -> None:
    logger.info("NOTIFICATION: Invoice %s generated for ₹%.2f", event.invoice_id, event.amount)
