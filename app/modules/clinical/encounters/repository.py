import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import Encounter
from app.modules.clinical.vitals.models import Vital
from app.shared.schemas.pagination import PaginationParams
from app.shared.utils.pagination import paginate


class EncounterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, encounter: Encounter) -> Encounter:
        self.session.add(encounter)
        await self.session.flush()
        await self.session.refresh(encounter)
        return encounter

    async def get_by_id(self, encounter_id: uuid.UUID, org_id: uuid.UUID) -> Encounter | None:
        result = await self.session.execute(
            select(Encounter)
            .where(
                Encounter.id == encounter_id,
                Encounter.organization_id == org_id,
                Encounter.deleted_at.is_(None),
            )
            .options(selectinload(Encounter.vitals), selectinload(Encounter.diagnoses))
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, params: PaginationParams
    ) -> tuple[list[Encounter], int]:
        query = (
            select(Encounter)
            .where(
                Encounter.patient_id == patient_id,
                Encounter.organization_id == org_id,
                Encounter.deleted_at.is_(None),
            )
            .order_by(Encounter.encounter_date.desc())
        )
        return await paginate(self.session, query, params)

    async def add_vital(self, vital: Vital) -> Vital:
        self.session.add(vital)
        await self.session.flush()
        return vital

    async def add_diagnosis(self, diagnosis: Diagnosis) -> Diagnosis:
        self.session.add(diagnosis)
        await self.session.flush()
        return diagnosis
