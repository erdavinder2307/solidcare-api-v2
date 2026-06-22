"""
Notification event handlers — wired to the event bus.
"""

import logging
import uuid
from dataclasses import dataclass

from app.core.events.bus import DomainEvent, event_bus
from app.core.background.tasks.notification_tasks import (
    send_email_notification,
    send_sms_notification,
)
from app.core.notifications.writer import create_in_app_notification
from app.modules.notifications.models import NotificationType

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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
    logger.info("NOTIFICATION: Appointment booked for patient %s", event.patient_id)
    await create_in_app_notification(
        DEFAULT_ORG_ID,
        None,
        NotificationType.APPOINTMENT_BOOKED,
        "Appointment booked",
        f"Appointment on {event.appointment_date} at {event.appointment_time}",
        event.patient_id,
    )

    sms_context = {
        "message": f"Appointment confirmed for {event.appointment_date} at {event.appointment_time}. - Solidcare"
    }
    email_context = {
        "subject": "Appointment confirmed",
        "body": f"Your appointment is booked for {event.appointment_date} at {event.appointment_time}.",
    }

    if event.patient_phone:
        send_sms_notification.delay(event.patient_phone, "appointment_booked", sms_context)
    if event.patient_email:
        send_email_notification.delay(event.patient_email, "appointment_booked", email_context)


@event_bus.subscribe(AppointmentCancelled)
async def on_appointment_cancelled(event: AppointmentCancelled) -> None:
    logger.info("NOTIFICATION: Appointment %s cancelled", event.appointment_id)
    await create_in_app_notification(
        DEFAULT_ORG_ID,
        None,
        NotificationType.APPOINTMENT_CANCELLED,
        "Appointment cancelled",
        event.reason or "Appointment was cancelled",
        event.patient_id,
    )


@event_bus.subscribe(PrescriptionGenerated)
async def on_prescription_generated(event: PrescriptionGenerated) -> None:
    logger.info("NOTIFICATION: Prescription %s ready", event.prescription_id)
    await create_in_app_notification(
        DEFAULT_ORG_ID,
        None,
        NotificationType.PRESCRIPTION_READY,
        "Prescription ready",
        "A prescription has been finalized and is ready",
        event.patient_id,
    )


@event_bus.subscribe(InvoiceGenerated)
async def on_invoice_generated(event: InvoiceGenerated) -> None:
    logger.info("NOTIFICATION: Invoice %s generated for ₹%.2f", event.invoice_id, event.amount)
    await create_in_app_notification(
        DEFAULT_ORG_ID,
        None,
        NotificationType.INVOICE_GENERATED,
        "Invoice generated",
        f"Invoice for ₹{event.amount:.2f} has been issued",
        event.patient_id,
    )
