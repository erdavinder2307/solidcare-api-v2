import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.clinical.encounters.models import Encounter
from app.modules.prescriptions.models import Prescription, PrescriptionItem
from app.shared.schemas.pagination import PaginationParams
from app.shared.utils.pagination import paginate


class PrescriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, prescription: Prescription, items: list[PrescriptionItem]) -> Prescription:
        self.session.add(prescription)
        await self.session.flush()
        for idx, item in enumerate(items):
            item.prescription_id = prescription.id
            item.sort_order = idx
            self.session.add(item)
        await self.session.flush()
        return await self.get_by_id(prescription.id)

    async def get_by_id(self, prescription_id: uuid.UUID) -> Prescription | None:
        result = await self.session.execute(
            select(Prescription)
            .where(Prescription.id == prescription_id, Prescription.deleted_at.is_(None))
            .options(selectinload(Prescription.items))
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_org(self, prescription_id: uuid.UUID, org_id: uuid.UUID) -> Prescription | None:
        result = await self.session.execute(
            select(Prescription)
            .join(Encounter, Prescription.encounter_id == Encounter.id)
            .where(
                Prescription.id == prescription_id,
                Encounter.organization_id == org_id,
                Prescription.deleted_at.is_(None),
            )
            .options(selectinload(Prescription.items))
        )
        return result.scalar_one_or_none()

    async def get_by_share_token(self, share_token: str) -> Prescription | None:
        result = await self.session.execute(
            select(Prescription)
            .where(
                Prescription.share_token == share_token,
                Prescription.deleted_at.is_(None),
            )
            .options(selectinload(Prescription.items))
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        patient_id: uuid.UUID | None = None,
    ) -> tuple[list[Prescription], int]:
        query = (
            select(Prescription)
            .join(Encounter, Prescription.encounter_id == Encounter.id)
            .where(Encounter.organization_id == org_id, Prescription.deleted_at.is_(None))
            .order_by(Prescription.created_at.desc())
        )
        if patient_id:
            query = query.where(Prescription.patient_id == patient_id)
        return await paginate(self.session, query, params)

    async def list_for_patient(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> list[Prescription]:
        result = await self.session.execute(
            select(Prescription)
            .join(Encounter, Prescription.encounter_id == Encounter.id)
            .where(
                Prescription.patient_id == patient_id,
                Encounter.organization_id == org_id,
                Prescription.deleted_at.is_(None),
            )
            .order_by(Prescription.created_at.desc())
            .options(selectinload(Prescription.items))
        )
        return list(result.scalars().all())
