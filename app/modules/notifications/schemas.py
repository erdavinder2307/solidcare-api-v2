import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.notifications.models import NotificationChannel, NotificationStatus, NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    channel: NotificationChannel
    notification_type: NotificationType
    status: NotificationStatus
    subject: str | None
    body: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
