import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.users.models import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_org(self, org_id: uuid.UUID) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.organization_id == org_id, User.deleted_at.is_(None))
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())
