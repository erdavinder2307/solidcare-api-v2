import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.users.models import Permission, Role, User, UserRole


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str, org_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.email == email.lower(), User.organization_id == org_id, User.deleted_at.is_(None))
            .options(selectinload(User.user_roles).selectinload(UserRole.role).selectinload(Role.role_permissions).selectinload(RolePermission.permission))  # noqa: F821
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc), failed_login_attempts=0)
        )

    async def increment_failed_attempts(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(User.failed_login_attempts).where(User.id == user_id)
        )
        current = result.scalar_one_or_none() or 0
        new_count = current + 1
        await self.session.execute(
            update(User).where(User.id == user_id).values(failed_login_attempts=new_count)
        )
        return new_count

    async def lock_user(self, user_id: uuid.UUID) -> None:
        from app.modules.users.models import UserStatus
        await self.session.execute(
            update(User).where(User.id == user_id).values(status=UserStatus.LOCKED)
        )

    async def update_mfa_secret(self, user_id: uuid.UUID, secret: str, backup_codes: list[str]) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(mfa_secret=secret, mfa_backup_codes=backup_codes, mfa_enabled=False)
        )

    async def enable_mfa(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(mfa_enabled=True)
        )

    async def disable_mfa(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(mfa_enabled=False, mfa_secret=None, mfa_backup_codes=None)
        )

    async def get_user_permissions(self, user_id: uuid.UUID) -> list[str]:
        result = await self.session.execute(
            select(Permission.slug)
            .join(RolePermission, Permission.id == RolePermission.permission_id)  # noqa: F821
            .join(Role, Role.id == RolePermission.role_id)  # noqa: F821
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.deleted_at.is_(None))
        )
        return list(set(result.scalars().all()))

    async def get_user_roles(self, user_id: uuid.UUID) -> list[str]:
        result = await self.session.execute(
            select(Role.slug)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.deleted_at.is_(None))
        )
        return list(set(result.scalars().all()))


# Import the missing model here to avoid circular imports
from app.modules.users.models import RolePermission  # noqa: E402
