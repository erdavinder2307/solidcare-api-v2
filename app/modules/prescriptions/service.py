import logging
import secrets
import uuid

from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.prescriptions.models import Prescription, PrescriptionItem, PrescriptionStatus
from app.modules.prescriptions.repository import PrescriptionRepository
from app.modules.prescriptions.schemas import PrescriptionCreate
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

logger = logging.getLogger(__name__)


class PrescriptionService:
    def __init__(
        self,
        repository: PrescriptionRepository,
        encounter_repository: EncounterRepository,
    ) -> None:
        self.repo = repository
        self.encounter_repo = encounter_repository

    async def create(self, org_id: uuid.UUID, data: PrescriptionCreate, created_by: uuid.UUID) -> Prescription:
        encounter = await self.encounter_repo.get_by_id(data.encounter_id, org_id)
        if not encounter:
            raise NotFoundError("Encounter", str(data.encounter_id))
        if encounter.patient_id != data.patient_id:
            raise BusinessRuleError("Patient does not match encounter")

        prescription = Prescription(
            encounter_id=data.encounter_id,
            patient_id=data.patient_id,
            doctor_id=data.doctor_id,
            clinic_id=data.clinic_id,
            diagnosis_summary=data.diagnosis_summary,
            notes=data.notes,
            status=PrescriptionStatus.DRAFT,
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        items = [
            PrescriptionItem(
                medicine_id=item.medicine_id,
                medicine_name=item.medicine_name,
                dosage=item.dosage,
                frequency=item.frequency,
                frequency_custom=item.frequency_custom,
                duration_days=item.duration_days,
                quantity=item.quantity,
                meal_relation=item.meal_relation,
                instructions=item.instructions,
            )
            for item in data.items
        ]
        return await self.repo.create(prescription, items)

    async def get(self, prescription_id: uuid.UUID, org_id: uuid.UUID) -> Prescription:
        prescription = await self.repo.get_by_id_for_org(prescription_id, org_id)
        if not prescription:
            raise NotFoundError("Prescription", str(prescription_id))
        return prescription

    async def list_prescriptions(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        patient_id: uuid.UUID | None = None,
    ) -> PaginatedResponse:
        items, total = await self.repo.list_for_org(org_id, params, patient_id)
        return PaginatedResponse.create(items, total, params)

    async def list_for_patient(self, patient_id: uuid.UUID, org_id: uuid.UUID) -> list[Prescription]:
        return await self.repo.list_for_patient(patient_id, org_id)

    async def finalize(self, prescription_id: uuid.UUID, org_id: uuid.UUID) -> Prescription:
        prescription = await self.get(prescription_id, org_id)
        if prescription.status != PrescriptionStatus.DRAFT:
            raise BusinessRuleError("Only draft prescriptions can be finalized")
        if not prescription.items:
            raise BusinessRuleError("Prescription must have at least one item")

        prescription.status = PrescriptionStatus.FINALIZED
        prescription.share_token = secrets.token_urlsafe(32)

        # Generate PDF
        try:
            from datetime import date
            from app.shared.services.pdf_service import (
                ClinicInfo, DoctorInfo, PatientInfo, PrescriptionItem as PdfItem,
                generate_prescription_pdf,
            )
            from app.modules.clinics.repository import ClinicRepository
            from app.modules.patients.repository import PatientRepository
            from app.modules.users.models import User
            from sqlalchemy import select

            # Load clinic
            clinic_repo = ClinicRepository(self.repo.session)
            clinic = await clinic_repo.get_by_id(prescription.clinic_id)
            clinic_info = ClinicInfo(
                name=clinic.name if clinic else "Clinic",
                address=", ".join(filter(None, [
                    getattr(clinic, "address_line1", None),
                    getattr(clinic, "city", None),
                    getattr(clinic, "state", None),
                ])) if clinic else "",
                phone=getattr(clinic, "phone", "") or "",
                gstin=getattr(clinic, "gstin", "") or "",
            )

            # Load doctor's user record
            doctor_result = await self.repo.session.execute(
                select(User).where(User.id == prescription.doctor_id)
            )
            doctor_user = doctor_result.scalar_one_or_none()
            doctor_info = DoctorInfo(
                full_name=doctor_user.full_name if doctor_user else "Doctor",
                registration_number="",
            )

            # Load patient
            patient_repo = PatientRepository(self.repo.session)
            patient = await patient_repo.get_by_id(prescription.patient_id, org_id)
            patient_info = PatientInfo(
                full_name=patient.full_name if patient else "Patient",
                uhid=patient.uhid if patient else "",
                phone=patient.phone if patient else "",
                abha_number=patient.abha_number if patient else None,
            )

            items = [
                PdfItem(
                    medicine_name=item.medicine_name,
                    dosage=item.dosage or "",
                    frequency=item.frequency.value if hasattr(item.frequency, "value") else (item.frequency or ""),
                    duration=str(item.duration_days) if item.duration_days else "",
                    meal_relation=item.meal_relation.value if hasattr(item.meal_relation, "value") else (item.meal_relation or ""),
                    instructions=item.instructions or "",
                )
                for item in prescription.items
            ]

            pdf_bytes = generate_prescription_pdf(
                clinic=clinic_info,
                doctor=doctor_info,
                patient=patient_info,
                prescription_id=str(prescription.id),
                prescription_date=date.today(),
                items=items,
                diagnosis_summary=prescription.diagnosis_summary,
                notes=prescription.notes,
            )

            # Upload to Azure Blob if configured, else store path marker
            blob_path = f"prescriptions/{prescription.id}.pdf"
            try:
                from app.core.storage.blob_service import upload_bytes
                blob_path = await upload_bytes(pdf_bytes, blob_path, content_type="application/pdf")
            except Exception:
                pass  # Blob upload optional — PDF still generated

            prescription.pdf_path = blob_path

        except Exception as exc:
            logger.warning("PDF generation failed for prescription %s: %s", prescription_id, exc)
            prescription.pdf_path = f"prescriptions/{prescription.id}.pdf"

        return prescription

    async def get_shared(self, share_token: str) -> Prescription:
        prescription = await self.repo.get_by_share_token(share_token)
        if not prescription or prescription.status != PrescriptionStatus.FINALIZED:
            raise NotFoundError("Prescription", "shared link")
        return prescription
