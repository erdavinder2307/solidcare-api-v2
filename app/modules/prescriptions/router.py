import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.prescriptions.models import FrequencyCode, MealRelation, PrescriptionStatus

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


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


class PrescriptionCreate(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    clinic_id: uuid.UUID
    diagnosis_summary: str | None = None
    notes: str | None = None
    items: list[PrescriptionItemCreate]


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

    model_config = {"from_attributes": True}


@router.post("", response_model=PrescriptionResponse, status_code=201)
async def create_prescription(
    payload: PrescriptionCreate,
    current_user: AuthRequired,
) -> PrescriptionResponse:
    current_user.require("prescription:create")
    return {"message": "Prescription created"}  # type: ignore


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: uuid.UUID,
    current_user: AuthRequired,
) -> PrescriptionResponse:
    current_user.require("prescription:read")
    return {"message": "Prescription detail"}  # type: ignore


@router.post("/{prescription_id}/finalize")
async def finalize_prescription(
    prescription_id: uuid.UUID,
    current_user: AuthRequired,
) -> dict:
    current_user.require("prescription:update")
    return {"message": "Prescription finalized and PDF generated"}


@router.get("/patient/{patient_id}", response_model=list[PrescriptionResponse])
async def list_patient_prescriptions(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
) -> list[PrescriptionResponse]:
    current_user.require("prescription:read")
    return []


@router.get("/share/{share_token}")
async def get_shared_prescription(share_token: str) -> dict:
    """Public endpoint for sharing prescriptions via link."""
    return {"message": "Shared prescription view"}
