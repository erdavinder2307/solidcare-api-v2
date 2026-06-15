import uuid
from datetime import UTC, datetime

from app.core.audit.writer import record_audit
from app.core.exceptions.errors import ConflictError, NotFoundError
from app.modules.audit.models import AuditAction
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
        created = await self.repo.create(patient)
        await record_audit(
            self.repo.session,
            action=AuditAction.CREATE,
            resource_type="patient",
            resource_id=str(created.id),
            organization_id=org_id,
            user_id=created_by,
            new_values={"uhid": created.uhid, "phone": created.phone},
        )
        return created

    async def search_duplicates(
        self,
        org_id: uuid.UUID,
        phone: str | None,
        first_name: str | None,
        last_name: str | None,
        abha_number: str | None,
    ) -> list[Patient]:
        return await self.repo.search_duplicates(org_id, phone, first_name, last_name, abha_number)

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
        await record_audit(
            self.repo.session,
            action=AuditAction.UPDATE,
            resource_type="patient",
            resource_id=str(patient_id),
            organization_id=org_id,
            user_id=updated_by,
            new_values=data.model_dump(exclude_none=True),
        )
        return patient

    async def delete(self, patient_id: uuid.UUID, org_id: uuid.UUID, deleted_by: uuid.UUID | None = None) -> None:
        patient = await self.get(patient_id, org_id)
        await self.repo.soft_delete(patient_id)
        await record_audit(
            self.repo.session,
            action=AuditAction.DELETE,
            resource_type="patient",
            resource_id=str(patient_id),
            organization_id=org_id,
            user_id=deleted_by,
            old_values={"uhid": patient.uhid},
        )

    async def update_consent(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, data: ConsentUpdate, recorded_by: uuid.UUID
    ) -> PatientConsent:
        await self.get(patient_id, org_id)
        consent = PatientConsent(
            patient_id=patient_id,
            consent_type=data.consent_type,
            consented=data.consented,
            consented_at=datetime.now(UTC) if data.consented else None,
            revoked_at=None if data.consented else datetime.now(UTC),
            notes=data.notes,
            created_by_id=recorded_by,
        )
        return await self.repo.add_consent(consent)

    async def upload_document(
        self,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
        document_type: str,
        file_name: str,
        content_type: str,
        file_bytes: bytes,
        notes: str | None,
        uploaded_by: uuid.UUID,
    ):
        from app.core.storage.blob_service import get_sas_url, upload_bytes
        from app.modules.patients.models import DocumentType, PatientDocument

        await self.get(patient_id, org_id)
        blob_name = f"patient-docs/{patient_id}/{uuid.uuid4()}_{file_name}"
        try:
            await upload_bytes(file_bytes, blob_name, content_type)
        except RuntimeError:
            pass  # storage not configured; store path anyway for local dev

        doc = PatientDocument(
            patient_id=patient_id,
            document_type=DocumentType(document_type),
            file_name=file_name,
            blob_path=blob_name,
            content_type=content_type,
            file_size_bytes=len(file_bytes),
            notes=notes,
            created_by_id=uploaded_by,
        )
        self.repo.session.add(doc)
        await self.repo.session.flush()
        await self.repo.session.refresh(doc)
        try:
            doc.download_url = get_sas_url(blob_name)
        except Exception:
            doc.download_url = None
        return doc

    async def list_documents(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> list:
        from sqlalchemy import select

        from app.core.storage.blob_service import get_sas_url
        from app.modules.patients.models import PatientDocument

        await self.get(patient_id, org_id)
        result = await self.repo.session.execute(
            select(PatientDocument)
            .where(
                PatientDocument.patient_id == patient_id,
                PatientDocument.deleted_at.is_(None),
            )
            .order_by(PatientDocument.created_at.desc())
        )
        docs = list(result.scalars().all())
        for doc in docs:
            try:
                doc.download_url = get_sas_url(doc.blob_path)
            except Exception:
                doc.download_url = None
        return docs

    async def delete_document(self, patient_id: uuid.UUID, document_id: uuid.UUID, org_id: uuid.UUID) -> None:
        from datetime import datetime

        from sqlalchemy import select

        from app.core.exceptions.errors import NotFoundError
        from app.modules.patients.models import PatientDocument

        await self.get(patient_id, org_id)
        result = await self.repo.session.execute(
            select(PatientDocument).where(
                PatientDocument.id == document_id,
                PatientDocument.patient_id == patient_id,
                PatientDocument.deleted_at.is_(None),
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise NotFoundError("PatientDocument", str(document_id))
        doc.deleted_at = datetime.now(UTC)
