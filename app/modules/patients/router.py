import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import (
    ConsentUpdate,
    PatientCreate,
    PatientDocumentResponse,
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


@router.get("/search-duplicates", response_model=list[PatientListItem], summary="Search for potential duplicate patients")
async def search_duplicates(
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
    phone: str | None = Query(default=None),
    first_name: str | None = Query(default=None),
    last_name: str | None = Query(default=None),
    abha_number: str | None = Query(default=None),
) -> list[PatientListItem]:
    current_user.require("patient:read")
    patients = await service.search_duplicates(
        current_user.org_id, phone, first_name, last_name, abha_number
    )
    return [PatientListItem.model_validate(p) for p in patients]


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
    await service.delete(patient_id, current_user.org_id, current_user.user_id)


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


@router.post("/{patient_id}/documents", response_model=PatientDocumentResponse, status_code=201, summary="Upload a patient document")
async def upload_document(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
    file: UploadFile = File(...),
    document_type: str = Form(default="other"),
    notes: str | None = Form(default=None),
) -> PatientDocumentResponse:
    current_user.require("patient:update")
    file_bytes = await file.read()
    doc = await service.upload_document(
        patient_id=patient_id,
        org_id=current_user.org_id,
        document_type=document_type,
        file_name=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
        notes=notes,
        uploaded_by=current_user.user_id,
    )
    return PatientDocumentResponse.model_validate(doc)


@router.get("/{patient_id}/documents", response_model=list[PatientDocumentResponse], summary="List patient documents")
async def list_documents(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> list[PatientDocumentResponse]:
    current_user.require("patient:read")
    docs = await service.list_documents(patient_id, current_user.org_id)
    return [PatientDocumentResponse.model_validate(d) for d in docs]


@router.delete("/{patient_id}/documents/{document_id}", status_code=204, summary="Delete a patient document")
async def delete_document(
    patient_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> None:
    current_user.require("patient:update")
    await service.delete_document(patient_id, document_id, current_user.org_id)
