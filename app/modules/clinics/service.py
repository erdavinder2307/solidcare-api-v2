import uuid

from app.core.exceptions.errors import NotFoundError
from app.modules.clinics.repository import ClinicRepository


class ClinicService:
    def __init__(self, repository: ClinicRepository) -> None:
        self.repo = repository

    async def list_clinics(self, org_id: uuid.UUID):
        return await self.repo.list_for_org(org_id)

    async def get_clinic(self, clinic_id: uuid.UUID, org_id: uuid.UUID):
        clinic = await self.repo.get_by_id(clinic_id, org_id)
        if not clinic:
            raise NotFoundError("Clinic", str(clinic_id))
        return clinic
