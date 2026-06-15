import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification, NotificationChannel


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        is_read: bool | None = None,
    ) -> tuple[list[Notification], int]:
        query = (
            select(Notification)
            .where(
                Notification.organization_id == org_id,
                Notification.user_id == user_id,
                Notification.channel == NotificationChannel.IN_APP,
                Notification.deleted_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
        )
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        result = await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total

    async def unread_count(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Notification.id)).where(
                Notification.organization_id == org_id,
                Notification.user_id == user_id,
                Notification.channel == NotificationChannel.IN_APP,
                Notification.is_read == False,  # noqa: E712
                Notification.deleted_at.is_(None),
            )
        )
        return result.scalar_one() or 0

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        return result.rowcount > 0

    async def mark_all_read(self, org_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.organization_id == org_id,
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        return result.rowcount

    async def create(self, notification: Notification) -> Notification:
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification
