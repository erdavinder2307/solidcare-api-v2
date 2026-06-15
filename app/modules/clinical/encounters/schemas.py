import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.modules.clinical.encounters.models import EncounterStatus, EncounterType


class InvoiceItemSuggestion(BaseModel):
    service_category: str
    description: str
    quantity: int
    unit_price: float
    tax_rate: float


class VitalCreate(BaseModel):
    systolic_bp: int | None = None
    diastolic_bp: int | None = None
    pulse_rate: int | None = None
    respiratory_rate: int | None = None
    temperature: float | None = None
    temperature_unit: str = "C"
    spo2: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    blood_glucose: float | None = None
    blood_glucose_type: str | None = None
    pain_scale: int | None = None
    notes: str | None = None


class DiagnosisCreate(BaseModel):
    icd10_code: str | None = None
    icd10_description: str | None = None
    custom_description: str | None = None
    diagnosis_type: str = "primary"
    is_chronic: bool = False
    notes: str | None = None


class EncounterCreate(BaseModel):
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    encounter_type: EncounterType = EncounterType.OPD
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    past_medical_history: str | None = None
    past_surgical_history: str | None = None
    family_history: str | None = None
    social_history: str | None = None
    general_examination: str | None = None
    systemic_examination: str | None = None
    clinical_impression: str | None = None
    treatment_plan: str | None = None
    follow_up_instructions: str | None = None
    follow_up_days: int | None = None
    referral_to: str | None = None
    referral_notes: str | None = None
    vitals: VitalCreate | None = None
    diagnoses: list[DiagnosisCreate] | None = None


class EncounterUpdate(BaseModel):
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    past_medical_history: str | None = None
    general_examination: str | None = None
    systemic_examination: str | None = None
    clinical_impression: str | None = None
    treatment_plan: str | None = None
    follow_up_instructions: str | None = None
    follow_up_days: int | None = None
    referral_to: str | None = None
    referral_notes: str | None = None


class VitalResponse(BaseModel):
    id: uuid.UUID
    systolic_bp: int | None
    diastolic_bp: int | None
    pulse_rate: int | None
    temperature: float | None
    spo2: int | None
    weight_kg: float | None
    recorded_at: datetime | None = None

    model_config = {"from_attributes": True}


class DiagnosisResponse(BaseModel):
    id: uuid.UUID
    icd10_code: str | None
    icd10_description: str | None
    custom_description: str | None
    diagnosis_type: str
    is_chronic: bool

    model_config = {"from_attributes": True}


class EncounterResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    appointment_id: uuid.UUID | None
    encounter_type: EncounterType
    status: EncounterStatus
    encounter_date: datetime
    chief_complaint: str | None
    history_of_present_illness: str | None
    general_examination: str | None
    clinical_impression: str | None
    treatment_plan: str | None
    follow_up_instructions: str | None
    follow_up_days: int | None
    referral_to: str | None
    summary_pdf_path: str | None
    completed_at: datetime | None
    attested_by_id: uuid.UUID | None
    attested_at: datetime | None
    created_at: datetime
    vitals: list[VitalResponse] = []
    diagnoses: list[DiagnosisResponse] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_encounter(cls, encounter) -> "EncounterResponse":
        return cls(
            id=encounter.id,
            organization_id=encounter.organization_id,
            clinic_id=encounter.clinic_id,
            patient_id=encounter.patient_id,
            doctor_id=encounter.doctor_id,
            appointment_id=encounter.appointment_id,
            encounter_type=encounter.encounter_type,
            status=encounter.status,
            encounter_date=encounter.encounter_date,
            chief_complaint=encounter.chief_complaint,
            history_of_present_illness=encounter.history_of_present_illness,
            general_examination=encounter.general_examination,
            clinical_impression=encounter.clinical_impression,
            treatment_plan=encounter.treatment_plan,
            follow_up_instructions=encounter.follow_up_instructions,
            follow_up_days=encounter.follow_up_days,
            referral_to=encounter.referral_to,
            summary_pdf_path=encounter.summary_pdf_path,
            completed_at=encounter.completed_at,
            created_at=encounter.created_at,
            vitals=[VitalResponse.model_validate(v) for v in (encounter.vitals or [])],
            diagnoses=[DiagnosisResponse.model_validate(d) for d in (encounter.diagnoses or [])],
        )
