import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.encounters.schemas import (
    EncounterCreate,
    EncounterResponse,
    EncounterUpdate,
)
from app.modules.clinical.encounters.service import EncounterService
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/encounters", tags=["Clinical Encounters"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> EncounterService:
    return EncounterService(EncounterRepository(session))


@router.post("", response_model=EncounterResponse, status_code=201)
async def create_encounter(
    payload: EncounterCreate,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:create")
    encounter = await service.create(current_user.org_id, payload, current_user.user_id)
    return EncounterResponse.model_validate(encounter)


@router.get("/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:read")
    encounter = await service.get(encounter_id, current_user.org_id)
    return EncounterResponse.model_validate(encounter)


@router.patch("/{encounter_id}", response_model=EncounterResponse)
async def update_encounter(
    encounter_id: uuid.UUID,
    payload: EncounterUpdate,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:update")
    encounter = await service.update(encounter_id, current_user.org_id, payload)
    return EncounterResponse.model_validate(encounter)


@router.post("/{encounter_id}/complete", response_model=EncounterResponse)
async def complete_encounter(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:update")
    encounter = await service.complete(encounter_id, current_user.org_id)
    return EncounterResponse.model_validate(encounter)


@router.get("/patient/{patient_id}", response_model=PaginatedResponse[EncounterResponse])
async def list_patient_encounters(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> PaginatedResponse:
    current_user.require("encounter:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list_for_patient(patient_id, current_user.org_id, params)
