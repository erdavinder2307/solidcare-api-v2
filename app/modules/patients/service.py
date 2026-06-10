import uuid
from datetime import datetime, timezone

from app.core.exceptions.errors import ConflictError, NotFoundError
from app.modules.patients.models import Patient, PatientConsent
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import ConsentUpdate, PatientCreate, PatientUpdate
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class PatientService:
    def __init__(self, repository: PatientRepository) -> None:
        self.repo = repository

    async def create(self, org_id: uuid.UUID, data: PatientCreate, created_by: uuid.UUID) -> Patient:
        existing = await self.repo.get_by_phone(data.phone, org_id)
        if existing:
            raise ConflictError(f"A patient with phone {data.phone} already exists (UHID: {existing.uhid})")

        uhid = await self.repo.generate_uhid(org_id)
        patient = Patient(
            organization_id=org_id,
            uhid=uhid,
            created_by_id=created_by,
            updated_by_id=created_by,
            **data.model_dump(),
        )
        return await self.repo.create(patient)

    async def get(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> Patient:
        patient = await self.repo.get_by_id(patient_id, org_id)
        if not patient:
            raise NotFoundError("Patient", str(patient_id))
        return patient

    async def list(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse:
        items, total = await self.repo.list(org_id, params, search, is_active)
        return PaginatedResponse.create(items, total, params)

    async def update(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, data: PatientUpdate, updated_by: uuid.UUID
    ) -> Patient:
        patient = await self.get(patient_id, org_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(patient, field, value)
        patient.updated_by_id = updated_by
        return patient

    async def delete(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> None:
        await self.get(patient_id, org_id)
        await self.repo.soft_delete(patient_id)

    async def update_consent(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, data: ConsentUpdate, recorded_by: uuid.UUID
    ) -> PatientConsent:
        await self.get(patient_id, org_id)
        consent = PatientConsent(
            patient_id=patient_id,
            consent_type=data.consent_type,
            consented=data.consented,
            consented_at=datetime.now(timezone.utc) if data.consented else None,
            revoked_at=None if data.consented else datetime.now(timezone.utc),
            notes=data.notes,
            created_by_id=recorded_by,
        )
        return await self.repo.add_consent(consent)
