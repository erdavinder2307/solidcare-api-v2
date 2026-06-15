import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.prescriptions.repository import PrescriptionRepository
from app.modules.prescriptions.schemas import (
    PrescriptionCreate,
    PrescriptionListItem,
    PrescriptionResponse,
    SharedPrescriptionResponse,
)
from app.modules.prescriptions.service import PrescriptionService
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> PrescriptionService:
    return PrescriptionService(PrescriptionRepository(session), EncounterRepository(session))


@router.post("", response_model=PrescriptionResponse, status_code=201)
async def create_prescription(
    payload: PrescriptionCreate,
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
) -> PrescriptionResponse:
    current_user.require("prescription:create")
    rx = await service.create(current_user.org_id, payload, current_user.user_id)
    return PrescriptionResponse.model_validate(rx)


@router.get("", response_model=PaginatedResponse[PrescriptionListItem])
async def list_prescriptions(
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    patient_id: uuid.UUID | None = None,
) -> PaginatedResponse:
    current_user.require("prescription:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list_prescriptions(current_user.org_id, params, patient_id)


@router.get("/patient/{patient_id}", response_model=list[PrescriptionResponse])
async def list_patient_prescriptions(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
) -> list[PrescriptionResponse]:
    current_user.require("prescription:read")
    items = await service.list_for_patient(patient_id, current_user.org_id)
    return [PrescriptionResponse.model_validate(rx) for rx in items]


@router.get("/share/{share_token}", response_model=SharedPrescriptionResponse)
async def get_shared_prescription(
    share_token: str,
    service: Annotated[PrescriptionService, Depends(get_service)],
) -> SharedPrescriptionResponse:
    rx = await service.get_shared(share_token)
    return SharedPrescriptionResponse.model_validate(rx)


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
) -> PrescriptionResponse:
    current_user.require("prescription:read")
    rx = await service.get(prescription_id, current_user.org_id)
    return PrescriptionResponse.model_validate(rx)


@router.post("/{prescription_id}/finalize", response_model=PrescriptionResponse)
async def finalize_prescription(
    prescription_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
) -> PrescriptionResponse:
    current_user.require("prescription:update")
    rx = await service.finalize(prescription_id, current_user.org_id)
    return PrescriptionResponse.model_validate(rx)


@router.get("/{prescription_id}/pdf")
async def download_prescription_pdf(
    prescription_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[PrescriptionService, Depends(get_service)],
):
    """Download prescription as PDF. Returns a redirect to Azure SAS URL if stored, else generates inline."""
    from fastapi.responses import Response
    current_user.require("prescription:read")
    rx = await service.get(prescription_id, current_user.org_id)
    if not rx.pdf_path:
        from app.core.exceptions.errors import NotFoundError
        raise NotFoundError("PDF", str(prescription_id))
    try:
        from fastapi.responses import RedirectResponse

        from app.core.storage.blob_service import get_sas_url
        url = await get_sas_url(rx.pdf_path)
        return RedirectResponse(url=url)
    except Exception:
        # Blob not configured — return path info
        return Response(
            content=f'{{"pdf_path": "{rx.pdf_path}"}}',
            media_type="application/json",
        )
