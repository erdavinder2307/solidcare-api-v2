import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinics.repository import ClinicRepository
from app.modules.clinics.schemas import ClinicResponse
from app.modules.clinics.service import ClinicService

router = APIRouter(prefix="/clinics", tags=["Clinics"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> ClinicService:
    return ClinicService(ClinicRepository(session))


@router.get("", response_model=list[ClinicResponse])
async def list_clinics(
    current_user: AuthRequired,
    service: Annotated[ClinicService, Depends(get_service)],
) -> list[ClinicResponse]:
    clinics = await service.list_clinics(current_user.org_id)
    return [ClinicResponse.model_validate(c) for c in clinics]


@router.get("/{clinic_id}", response_model=ClinicResponse)
async def get_clinic(
    clinic_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[ClinicService, Depends(get_service)],
) -> ClinicResponse:
    clinic = await service.get_clinic(clinic_id, current_user.org_id)
    return ClinicResponse.model_validate(clinic)
