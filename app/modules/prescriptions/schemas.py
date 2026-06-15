import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.prescriptions.models import FrequencyCode, MealRelation, PrescriptionStatus


class PrescriptionItemCreate(BaseModel):
    medicine_id: uuid.UUID | None = None
    medicine_name: str
    dosage: str | None = None
    frequency: FrequencyCode
    frequency_custom: str | None = None
    duration_days: int | None = None
    quantity: str | None = None
    meal_relation: MealRelation = MealRelation.AFTER_FOOD
    instructions: str | None = None


class PrescriptionItemResponse(BaseModel):
    id: uuid.UUID
    medicine_id: uuid.UUID | None
    medicine_name: str
    dosage: str | None
    frequency: FrequencyCode
    frequency_custom: str | None
    duration_days: int | None
    quantity: str | None
    meal_relation: MealRelation
    instructions: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class PrescriptionCreate(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    diagnosis_summary: str | None = None
    notes: str | None = None
    items: list[PrescriptionItemCreate] = Field(min_length=1)


class PrescriptionResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    status: PrescriptionStatus
    notes: str | None
    diagnosis_summary: str | None
    pdf_path: str | None
    share_token: str | None
    created_at: datetime
    items: list[PrescriptionItemResponse] = []

    model_config = {"from_attributes": True}


class PrescriptionListItem(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    status: PrescriptionStatus
    diagnosis_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SharedPrescriptionResponse(BaseModel):
    id: uuid.UUID
    status: PrescriptionStatus
    diagnosis_summary: str | None
    notes: str | None
    created_at: datetime
    items: list[PrescriptionItemResponse]

    model_config = {"from_attributes": True}
