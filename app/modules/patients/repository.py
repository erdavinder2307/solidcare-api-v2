import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.patients.models import Patient, PatientConsent, PatientDocument
from app.shared.schemas.pagination import PaginationParams
from app.shared.utils.pagination import paginate


class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, patient: Patient) -> Patient:
        self.session.add(patient)
        await self.session.flush()
        await self.session.refresh(patient)
        return patient

    async def get_by_id(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> Patient | None:
        result = await self.session.execute(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.organization_id == org_id,
                Patient.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str, org_id: uuid.UUID) -> Patient | None:
        result = await self.session.execute(
            select(Patient).where(
                Patient.phone == phone,
                Patient.organization_id == org_id,
                Patient.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_uhid(self, uhid: str, org_id: uuid.UUID) -> Patient | None:
        result = await self.session.execute(
            select(Patient).where(
                Patient.uhid == uhid,
                Patient.organization_id == org_id,
                Patient.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Patient], int]:
        query = select(Patient).where(
            Patient.organization_id == org_id, Patient.deleted_at.is_(None)
        )
        if search:
            query = query.where(
                or_(
                    func.lower(func.concat(Patient.first_name, " ", Patient.last_name)).contains(search.lower()),
                    Patient.phone.contains(search),
                    Patient.uhid.contains(search.upper()),
                )
            )
        if is_active is not None:
            query = query.where(Patient.is_active == is_active)

        query = query.order_by(Patient.created_at.desc())
        return await paginate(self.session, query, params)

    async def generate_uhid(self, org_id: uuid.UUID) -> str:
        result = await self.session.execute(
            select(func.count(Patient.id)).where(Patient.organization_id == org_id)
        )
        count = result.scalar_one() or 0
        return f"PT{count + 1:06d}"

    async def soft_delete(self, patient_id: uuid.UUID) -> None:
        from datetime import datetime, timezone
        from sqlalchemy import update
        await self.session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )

    async def add_consent(self, consent: PatientConsent) -> PatientConsent:
        self.session.add(consent)
        await self.session.flush()
        return consent
