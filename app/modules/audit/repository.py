import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_logs(
        self,
        org_id: uuid.UUID,
        page: int,
        page_size: int,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog).where(AuditLog.organization_id == org_id).order_by(AuditLog.created_at.desc())
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if action:
            query = query.where(AuditLog.action == action)
        if from_date:
            start = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            query = query.where(AuditLog.created_at >= start)
        if to_date:
            end = datetime.combine(to_date, time.max, tzinfo=timezone.utc)
            query = query.where(AuditLog.created_at <= end)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total
