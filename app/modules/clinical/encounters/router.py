import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.encounters.schemas import (
    DiagnosisCreate,
    DiagnosisResponse,
    EncounterCreate,
    EncounterResponse,
    EncounterUpdate,
    InvoiceItemSuggestion,
    VitalCreate,
    VitalResponse,
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
    loaded = await service.get(encounter.id, current_user.org_id)
    return EncounterResponse.from_encounter(loaded)


@router.get("/for-appointment/{appointment_id}", response_model=EncounterResponse | None)
async def get_for_appointment(
    appointment_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse | None:
    """Find an existing encounter for a given appointment (nurse pre-entry lookup)."""
    current_user.require("encounter:read")
    encounter = await service.get_for_appointment(appointment_id, current_user.org_id)
    if encounter is None:
        return None
    return EncounterResponse.from_encounter(encounter)


@router.get("/{encounter_id}/invoice-items", response_model=list[InvoiceItemSuggestion])
async def get_invoice_items(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> list[InvoiceItemSuggestion]:
    """Return suggested invoice line items derived from an encounter."""
    current_user.require("encounter:read")
    return await service.get_invoice_items(encounter_id, current_user.org_id)


@router.get("/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:read")
    encounter = await service.get(encounter_id, current_user.org_id)
    return EncounterResponse.from_encounter(encounter)


@router.patch("/{encounter_id}", response_model=EncounterResponse)
async def update_encounter(
    encounter_id: uuid.UUID,
    payload: EncounterUpdate,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:update")
    encounter = await service.update(encounter_id, current_user.org_id, payload)
    loaded = await service.get(encounter.id, current_user.org_id)
    return EncounterResponse.from_encounter(loaded)


@router.post("/{encounter_id}/complete", response_model=EncounterResponse)
async def complete_encounter(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:update")
    await service.complete(encounter_id, current_user.org_id)
    encounter = await service.get(encounter_id, current_user.org_id)
    return EncounterResponse.from_encounter(encounter)


@router.post("/{encounter_id}/attest", response_model=EncounterResponse)
async def attest_encounter(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> EncounterResponse:
    current_user.require("encounter:update")
    await service.attest(encounter_id, current_user.org_id, current_user.user_id)
    encounter = await service.get(encounter_id, current_user.org_id)
    return EncounterResponse.from_encounter(encounter)


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
    result = await service.list_for_patient(patient_id, current_user.org_id, params)
    mapped = [EncounterResponse.from_encounter(e) for e in result.items]
    return PaginatedResponse.create(mapped, result.total, params)


@router.post("/{encounter_id}/diagnoses", response_model=DiagnosisResponse, status_code=201)
async def add_diagnosis(
    encounter_id: uuid.UUID,
    payload: DiagnosisCreate,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> DiagnosisResponse:
    current_user.require("encounter:update")
    dx = await service.add_diagnosis(encounter_id, current_user.org_id, payload)
    return DiagnosisResponse.model_validate(dx)


@router.delete("/{encounter_id}/diagnoses/{diagnosis_id}", status_code=204)
async def remove_diagnosis(
    encounter_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> None:
    current_user.require("encounter:update")
    await service.remove_diagnosis(encounter_id, diagnosis_id, current_user.org_id)


@router.post("/{encounter_id}/vitals", response_model=VitalResponse, status_code=201)
async def add_vitals(
    encounter_id: uuid.UUID,
    payload: VitalCreate,
    current_user: AuthRequired,
    service: Annotated[EncounterService, Depends(get_service)],
) -> VitalResponse:
    current_user.require("encounter:update")
    vital = await service.add_vitals(encounter_id, current_user.org_id, payload)
    return VitalResponse.model_validate(vital)
