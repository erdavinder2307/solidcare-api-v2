import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinics.models import Clinic


class ClinicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_org(self, org_id: uuid.UUID) -> list[Clinic]:
        result = await self.session.execute(
            select(Clinic).where(
                Clinic.organization_id == org_id,
                Clinic.deleted_at.is_(None),
                Clinic.is_active == True,  # noqa: E712
            ).order_by(Clinic.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, clinic_id: uuid.UUID, org_id: uuid.UUID) -> Clinic | None:
        result = await self.session.execute(
            select(Clinic).where(
                Clinic.id == clinic_id,
                Clinic.organization_id == org_id,
                Clinic.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
