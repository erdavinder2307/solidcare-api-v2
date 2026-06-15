import uuid

from app.core.exceptions.errors import NotFoundError
from app.modules.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.modules.notifications.repository import NotificationRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class NotificationService:
    def __init__(self, repository: NotificationRepository) -> None:
        self.repo = repository

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        params: PaginationParams,
        is_read: bool | None = None,
    ) -> PaginatedResponse:
        items, total = await self.repo.list_for_user(org_id, user_id, params.page, params.page_size, is_read)
        return PaginatedResponse.create(items, total, params)

    async def unread_count(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return await self.repo.unread_count(org_id, user_id)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if not await self.repo.mark_read(notification_id, user_id):
            raise NotFoundError("Notification", str(notification_id))

    async def mark_all_read(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return await self.repo.mark_all_read(org_id, user_id)

    async def create_in_app(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        notification_type: NotificationType,
        subject: str,
        body: str,
        patient_id: uuid.UUID | None = None,
    ) -> Notification:
        notification = Notification(
            organization_id=org_id,
            user_id=user_id,
            patient_id=patient_id,
            channel=NotificationChannel.IN_APP,
            notification_type=notification_type,
            status=NotificationStatus.DELIVERED,
            recipient_address=str(user_id or patient_id or org_id),
            subject=subject,
            body=body,
            is_read=False,
        )
        return await self.repo.create(notification)
