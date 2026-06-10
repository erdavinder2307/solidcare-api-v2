import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import (
    ConsentUpdate,
    PatientCreate,
    PatientListItem,
    PatientResponse,
    PatientUpdate,
)
from app.modules.patients.service import PatientService
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/patients", tags=["Patients"])


def get_patient_service(session: Annotated[AsyncSession, Depends(get_db)]) -> PatientService:
    return PatientService(PatientRepository(session))


@router.post("", response_model=PatientResponse, status_code=201, summary="Register a new patient")
async def create_patient(
    payload: PatientCreate,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> PatientResponse:
    current_user.require("patient:create")
    patient = await service.create(current_user.org_id, payload, current_user.user_id)
    return PatientResponse.model_validate(patient)


@router.get("", response_model=PaginatedResponse[PatientListItem], summary="List patients")
async def list_patients(
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> PaginatedResponse:
    current_user.require("patient:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list(current_user.org_id, params, search, is_active)


@router.get("/{patient_id}", response_model=PatientResponse, summary="Get patient by ID")
async def get_patient(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> PatientResponse:
    current_user.require("patient:read")
    patient = await service.get(patient_id, current_user.org_id)
    return PatientResponse.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientResponse, summary="Update patient")
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> PatientResponse:
    current_user.require("patient:update")
    patient = await service.update(patient_id, current_user.org_id, payload, current_user.user_id)
    return PatientResponse.model_validate(patient)


@router.delete("/{patient_id}", status_code=204, summary="Soft-delete patient")
async def delete_patient(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> None:
    current_user.require("patient:delete")
    await service.delete(patient_id, current_user.org_id)


@router.post("/{patient_id}/consent", summary="Record patient consent")
async def update_consent(
    patient_id: uuid.UUID,
    payload: ConsentUpdate,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> dict:
    current_user.require("patient:update")
    await service.update_consent(patient_id, current_user.org_id, payload, current_user.user_id)
    return {"message": "Consent recorded"}
