import logging

from app.core.background.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.core.background.tasks.notification_tasks.send_appointment_reminders", bind=True, max_retries=3)
def send_appointment_reminders(self, hours_before: int = 24) -> dict:
    """Periodic task: fetch upcoming appointments and send reminders."""
    logger.info("Running appointment reminder task for %dh window", hours_before)
    # Database query and notification dispatch implemented in Phase 8
    return {"status": "scheduled", "hours_before": hours_before}


@celery_app.task(bind=True, max_retries=3)
def send_email_notification(self, to_email: str, template: str, context: dict) -> bool:
    logger.info("Sending email to %s via template %s", to_email, template)
    return True


@celery_app.task(bind=True, max_retries=3)
def send_sms_notification(self, phone: str, template: str, context: dict) -> bool:
    logger.info("Sending SMS to %s via template %s", phone, template)
    return True
