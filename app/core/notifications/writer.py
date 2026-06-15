"""Persist in-app notifications from domain events."""

import logging
import uuid

from app.database import get_db_context
from app.modules.notifications.models import NotificationType
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService

logger = logging.getLogger(__name__)


async def create_in_app_notification(
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    notification_type: NotificationType,
    subject: str,
    body: str,
    patient_id: uuid.UUID | None = None,
) -> None:
    try:
        async with get_db_context() as session:
            service = NotificationService(NotificationRepository(session))
            await service.create_in_app(org_id, user_id, notification_type, subject, body, patient_id)
    except Exception:
        logger.exception("Failed to persist in-app notification")
