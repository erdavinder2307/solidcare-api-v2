import asyncio
import logging

from app.core.background.celery_app import celery_app
from app.shared.services.notification_delivery import (
    send_email_via_sendgrid,
    send_sms_via_msg91,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="app.core.background.tasks.notification_tasks.send_appointment_reminders", bind=True, max_retries=3)
def send_appointment_reminders(self, hours_before: int | None = None) -> dict:
    """Periodic task: send reminders for appointments starting within `hours_before`
    hours (default: settings.REMINDER_LEAD_HOURS). Does nothing unless
    REMINDERS_ENABLED is true. Safe to retry or run concurrently: each
    appointment + reminder kind is claimed in appointment_reminders before sending."""
    from app.config import settings
    from app.modules.notifications.reminders import run_appointment_reminders

    return asyncio.run(run_appointment_reminders(hours_before, settings=settings))


@celery_app.task(bind=True, max_retries=3)
def send_email_notification(self, to_email: str, template: str, context: dict) -> bool:
    logger.info("Sending email to %s via template %s", to_email, template)
    subject = context.get("subject") or f"Solidcare notification: {template.replace('_', ' ').title()}"
    body_text = context.get("body") or "You have a new update from Solidcare."
    body_html = context.get("html")
    return send_email_via_sendgrid(to_email, subject, body_text, body_html)


@celery_app.task(bind=True, max_retries=3)
def send_sms_notification(self, phone: str, template: str, context: dict) -> bool:
    logger.info("Sending SMS to %s via template %s", phone, template)
    message = context.get("message") or context.get("body") or "You have an update from Solidcare."
    return send_sms_via_msg91(phone, message)
