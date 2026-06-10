import uuid
from datetime import datetime, timezone

from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import Encounter, EncounterStatus
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.encounters.schemas import EncounterCreate, EncounterUpdate
from app.modules.clinical.vitals.models import Vital
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class EncounterService:
    def __init__(self, repository: EncounterRepository) -> None:
        self.repo = repository

    async def create(self, org_id: uuid.UUID, data: EncounterCreate, created_by: uuid.UUID) -> Encounter:
        encounter = Encounter(
            organization_id=org_id,
            encounter_date=datetime.now(timezone.utc),
            created_by_id=created_by,
            **data.model_dump(exclude={"vitals", "diagnoses"}),
        )
        encounter = await self.repo.create(encounter)

        if data.vitals:
            vital = Vital(
                encounter_id=encounter.id,
                patient_id=encounter.patient_id,
                recorded_at=datetime.now(timezone.utc),
                **data.vitals.model_dump(),
            )
            await self.repo.add_vital(vital)

        for dx_data in (data.diagnoses or []):
            diagnosis = Diagnosis(
                encounter_id=encounter.id,
                patient_id=encounter.patient_id,
                **dx_data.model_dump(),
            )
            await self.repo.add_diagnosis(diagnosis)

        return encounter

    async def get(self, encounter_id: uuid.UUID, org_id: uuid.UUID) -> Encounter:
        encounter = await self.repo.get_by_id(encounter_id, org_id)
        if not encounter:
            raise NotFoundError("Encounter", str(encounter_id))
        return encounter

    async def update(self, encounter_id: uuid.UUID, org_id: uuid.UUID, data: EncounterUpdate) -> Encounter:
        encounter = await self.get(encounter_id, org_id)
        if encounter.status == EncounterStatus.COMPLETED:
            raise BusinessRuleError("Cannot modify a completed encounter")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(encounter, field, value)
        return encounter

    async def complete(self, encounter_id: uuid.UUID, org_id: uuid.UUID) -> Encounter:
        encounter = await self.get(encounter_id, org_id)
        if encounter.status == EncounterStatus.COMPLETED:
            raise BusinessRuleError("Encounter is already completed")
        encounter.status = EncounterStatus.COMPLETED
        encounter.completed_at = datetime.now(timezone.utc)
        return encounter

    async def list_for_patient(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, params: PaginationParams
    ) -> PaginatedResponse:
        items, total = await self.repo.list_for_patient(patient_id, org_id, params)
        return PaginatedResponse.create(items, total, params)
