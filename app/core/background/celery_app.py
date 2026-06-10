from celery import Celery

from app.config import settings

celery_app = Celery(
    "solidcare",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.core.background.tasks.notification_tasks",
        "app.core.background.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "appointment-reminders-24h": {
            "task": "app.core.background.tasks.notification_tasks.send_appointment_reminders",
            "schedule": 3600.0,
            "kwargs": {"hours_before": 24},
        },
        "appointment-reminders-2h": {
            "task": "app.core.background.tasks.notification_tasks.send_appointment_reminders",
            "schedule": 1800.0,
            "kwargs": {"hours_before": 2},
        },
    },
)
