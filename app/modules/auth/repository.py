import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.organizations.models import Membership, MembershipStatus
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
            .values(last_login_at=datetime.now(UTC), failed_login_attempts=0)
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

    async def get_user_permissions(self, user_id: uuid.UUID, org_id: uuid.UUID | None = None) -> list[str]:
        """Permissions granted to a user, optionally scoped to a single organization.

        `org_id=None` (legacy call sites) returns permissions from ALL of the user's
        role assignments regardless of org — safe only while every user has a single
        membership. Once a user can hold roles in more than one org (post-F4
        invitations), callers on an authenticated request path MUST pass `org_id` to
        avoid granting one org's permissions inside another org's session. `Role`
        rows always carry an `organization_id` in current seed/usage; a role with a
        NULL `organization_id` (if one is ever introduced as a truly global system
        role) matches every org.
        """
        query = (
            select(Permission.slug)
            .join(RolePermission, Permission.id == RolePermission.permission_id)  # noqa: F821
            .join(Role, Role.id == RolePermission.role_id)  # noqa: F821
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.deleted_at.is_(None))
        )
        if org_id is not None:
            query = query.where((Role.organization_id.is_(None)) | (Role.organization_id == org_id))
        result = await self.session.execute(query)
        return list(set(result.scalars().all()))

    async def get_user_roles(self, user_id: uuid.UUID, org_id: uuid.UUID | None = None) -> list[str]:
        """Role slugs for a user, optionally scoped to a single organization.

        See `get_user_permissions` for why `org_id` matters once a user can belong
        to more than one org.
        """
        query = (
            select(Role.slug)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.deleted_at.is_(None))
        )
        if org_id is not None:
            query = query.where((Role.organization_id.is_(None)) | (Role.organization_id == org_id))
        result = await self.session.execute(query)
        return list(set(result.scalars().all()))

    async def has_active_membership(self, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(Membership.id).where(
                Membership.user_id == user_id,
                Membership.organization_id == org_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_user_memberships(self, user_id: uuid.UUID) -> list[Membership]:
        """Active org memberships for a user, most recently created first.

        Additive alongside `users.organization_id` — not yet used to resolve which
        org a request is scoped to (see ROADMAP.md F2). Currently only surfaced on
        the JWT so clients can start rendering a workspace switcher.
        """
        result = await self.session.execute(
            select(Membership)
            .where(
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.deleted_at.is_(None),
            )
            .order_by(Membership.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_clinic_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(UserRole.clinic_id).where(
                UserRole.user_id == user_id,
                UserRole.clinic_id.is_not(None),
                UserRole.deleted_at.is_(None),
            )
        )
        clinic_ids = [row[0] for row in result.all() if row[0]]
        if clinic_ids:
            return list(set(clinic_ids))

        from app.modules.doctors.models import Doctor, DoctorClinicAssignment

        doctor_result = await self.session.execute(
            select(DoctorClinicAssignment.clinic_id)
            .join(Doctor, Doctor.id == DoctorClinicAssignment.doctor_id)
            .where(Doctor.user_id == user_id, Doctor.deleted_at.is_(None))
        )
        return list(set(row[0] for row in doctor_result.all() if row[0]))


# Import the missing model here to avoid circular imports
from app.modules.users.models import RolePermission  # noqa: E402
