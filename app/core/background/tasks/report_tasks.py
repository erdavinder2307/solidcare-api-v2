import logging

from app.core.background.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def generate_daily_report(self, org_id: str, clinic_id: str, report_date: str) -> dict:
    logger.info("Generating daily OPD report for clinic %s on %s", clinic_id, report_date)
    return {"status": "queued"}


@celery_app.task(bind=True, max_retries=2)
def generate_monthly_revenue_report(self, org_id: str, clinic_id: str, year: int, month: int) -> dict:
    logger.info("Generating monthly revenue report for clinic %s – %d/%d", clinic_id, year, month)
    return {"status": "queued"}
