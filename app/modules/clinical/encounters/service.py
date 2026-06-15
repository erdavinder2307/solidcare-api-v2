import uuid
from datetime import UTC, datetime

from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import Encounter, EncounterStatus
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.encounters.schemas import (
    DiagnosisCreate,
    EncounterCreate,
    EncounterUpdate,
    VitalCreate,
)
from app.modules.clinical.vitals.models import Vital
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class EncounterService:
    def __init__(self, repository: EncounterRepository) -> None:
        self.repo = repository

    async def create(self, org_id: uuid.UUID, data: EncounterCreate, created_by: uuid.UUID) -> Encounter:
        encounter = Encounter(
            organization_id=org_id,
            encounter_date=datetime.now(UTC),
            created_by_id=created_by,
            **data.model_dump(exclude={"vitals", "diagnoses"}),
        )
        encounter = await self.repo.create(encounter)

        if data.vitals:
            vital = Vital(
                encounter_id=encounter.id,
                patient_id=encounter.patient_id,
                recorded_at=datetime.now(UTC),
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
        encounter.completed_at = datetime.now(UTC)
        await self._generate_summary_pdf(encounter, org_id)
        return encounter

    async def attest(
        self, encounter_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> Encounter:
        encounter = await self.get(encounter_id, org_id)
        if encounter.status != EncounterStatus.COMPLETED:
            raise BusinessRuleError("Only completed encounters can be attested")
        if encounter.attested_at is not None:
            raise BusinessRuleError("Encounter has already been attested")
        encounter.attested_by_id = user_id
        encounter.attested_at = datetime.now(UTC)
        return encounter

    async def _generate_summary_pdf(self, encounter: Encounter, org_id: uuid.UUID) -> None:
        """Generate encounter summary PDF. Non-blocking on failure."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from sqlalchemy import select

            from app.modules.clinics.models import Clinic
            from app.modules.patients.models import Patient
            from app.modules.users.models import User
            from app.shared.services.pdf_service import (
                ClinicInfo,
                DoctorInfo,
                PatientInfo,
                generate_encounter_summary_pdf,
            )

            session = self.repo.session
            clinic_row = (await session.execute(
                select(Clinic).where(Clinic.id == encounter.clinic_id)
            )).scalar_one_or_none()
            patient_row = (await session.execute(
                select(Patient).where(Patient.id == encounter.patient_id)
            )).scalar_one_or_none()
            doctor_row = (await session.execute(
                select(User).where(User.id == encounter.doctor_id)
            )).scalar_one_or_none()

            clinic_info = ClinicInfo(
                name=clinic_row.name if clinic_row else "SolidCare Clinic",
                address=", ".join(filter(None, [
                    getattr(clinic_row, "address_line1", None),
                    getattr(clinic_row, "city", None),
                    getattr(clinic_row, "state", None),
                ])) if clinic_row else "",
                phone=getattr(clinic_row, "phone", "") or "",
                email=getattr(clinic_row, "email", "") or "",
            )
            doctor_info = DoctorInfo(
                full_name=doctor_row.full_name if doctor_row else "Doctor",
                registration_number=getattr(doctor_row, "medical_registration_number", None),
                specialization=None,
            )
            patient_info = PatientInfo(
                full_name=patient_row.full_name if patient_row else "Unknown",
                patient_id=str(encounter.patient_id),
                dob=str(patient_row.date_of_birth) if patient_row and patient_row.date_of_birth else None,
                phone=getattr(patient_row, "phone", None),
            )

            soap = {
                "subjective": encounter.chief_complaint,
                "objective": encounter.general_examination,
                "assessment": encounter.clinical_impression,
                "plan": encounter.treatment_plan,
            }
            vitals = {}
            diagnoses = [d.diagnosis_name for d in (encounter.diagnoses or [])]

            pdf_bytes = generate_encounter_summary_pdf(
                clinic=clinic_info,
                doctor=doctor_info,
                patient=patient_info,
                encounter_id=str(encounter.id),
                encounter_date=encounter.encounter_date.strftime("%Y-%m-%d") if encounter.encounter_date else "",
                soap=soap,
                vitals=vitals,
                diagnoses=diagnoses,
            )
            blob_name = f"encounters/{encounter.id}_summary.pdf"
            try:
                from app.core.storage.blob_service import upload_bytes
                await upload_bytes(pdf_bytes, blob_name, "application/pdf")
            except RuntimeError:
                pass
            encounter.summary_pdf_path = blob_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("Encounter summary PDF failed for %s: %s", encounter.id, exc)

    async def get_for_appointment(
        self, appointment_id: uuid.UUID, org_id: uuid.UUID
    ) -> "Encounter | None":
        from sqlalchemy import select
        result = await self.repo.session.execute(
            select(Encounter)
            .where(
                Encounter.appointment_id == appointment_id,
                Encounter.organization_id == org_id,
                Encounter.deleted_at.is_(None),
            )
            .order_by(Encounter.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_vitals(
        self, encounter_id: uuid.UUID, org_id: uuid.UUID, data: VitalCreate
    ) -> Vital:
        encounter = await self.get(encounter_id, org_id)
        vital = Vital(
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            recorded_at=datetime.now(UTC),
            **data.model_dump(),
        )
        return await self.repo.add_vital(vital)

    async def add_diagnosis(
        self, encounter_id: uuid.UUID, org_id: uuid.UUID, data: DiagnosisCreate
    ) -> Diagnosis:
        encounter = await self.get(encounter_id, org_id)
        if encounter.status == EncounterStatus.COMPLETED:
            raise BusinessRuleError("Cannot modify a completed encounter")
        diagnosis = Diagnosis(
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            **data.model_dump(),
        )
        return await self.repo.add_diagnosis(diagnosis)

    async def remove_diagnosis(
        self, encounter_id: uuid.UUID, diagnosis_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        from sqlalchemy import delete
        encounter = await self.get(encounter_id, org_id)
        if encounter.status == EncounterStatus.COMPLETED:
            raise BusinessRuleError("Cannot modify a completed encounter")
        await self.repo.session.execute(
            delete(Diagnosis).where(
                Diagnosis.id == diagnosis_id,
                Diagnosis.encounter_id == encounter.id,
            )
        )

    async def list_for_patient(
        self, patient_id: uuid.UUID, org_id: uuid.UUID, params: PaginationParams
    ) -> PaginatedResponse:
        items, total = await self.repo.list_for_patient(patient_id, org_id, params)
        return PaginatedResponse.create(items, total, params)

    async def get_invoice_items(
        self, encounter_id: uuid.UUID, org_id: uuid.UUID
    ) -> list:
        """Return suggested invoice line items derived from an encounter (consultation fee, lab tests, pharmacy)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.modules.clinical.encounters.schemas import InvoiceItemSuggestion
        from app.modules.clinical.lab_orders.models import LabOrder
        from app.modules.doctors.models import Doctor
        from app.modules.prescriptions.models import Prescription

        stmt = (
            select(Encounter)
            .where(
                Encounter.id == encounter_id,
                Encounter.organization_id == org_id,
                Encounter.deleted_at.is_(None),
            )
            .options(
                selectinload(Encounter.lab_orders).selectinload(LabOrder.items),
                selectinload(Encounter.prescriptions).selectinload(Prescription.items),
            )
        )
        result = await self.repo.session.execute(stmt)
        encounter = result.scalar_one_or_none()
        if not encounter:
            raise NotFoundError("Encounter", str(encounter_id))

        doctor_result = await self.repo.session.execute(
            select(Doctor).where(Doctor.id == encounter.doctor_id)
        )
        doctor = doctor_result.scalar_one_or_none()
        fee = (doctor.consultation_fee or 500.0) if doctor else 500.0

        suggestions: list[InvoiceItemSuggestion] = [
            InvoiceItemSuggestion(
                service_category="consultation",
                description="Consultation fee",
                quantity=1,
                unit_price=fee,
                tax_rate=0.0,
            )
        ]

        for order in (encounter.lab_orders or []):
            for item in (order.items or []):
                suggestions.append(InvoiceItemSuggestion(
                    service_category="lab",
                    description=item.test_name,
                    quantity=1,
                    unit_price=0.0,
                    tax_rate=0.0,
                ))

        for rx in (encounter.prescriptions or []):
            for item in (rx.items or []):
                desc = item.medicine_name
                if item.dosage:
                    desc = f"{desc} {item.dosage}"
                suggestions.append(InvoiceItemSuggestion(
                    service_category="pharmacy",
                    description=desc,
                    quantity=1,
                    unit_price=0.0,
                    tax_rate=0.0,
                ))

        return suggestions

