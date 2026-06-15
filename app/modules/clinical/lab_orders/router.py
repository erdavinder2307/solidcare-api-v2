import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.lab_orders.repository import LabOrderRepository
from app.modules.clinical.lab_orders.schemas import (
    LabOrderCreate,
    LabOrderResponse,
    LabOrderWithResultsResponse,
    LabResultCreate,
)
from app.modules.clinical.lab_orders.service import LabOrderService

router = APIRouter(prefix="/lab-orders", tags=["Lab Orders"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> LabOrderService:
    return LabOrderService(LabOrderRepository(session), EncounterRepository(session))


@router.post("", response_model=LabOrderResponse, status_code=201)
async def create_lab_order(
    payload: LabOrderCreate,
    current_user: AuthRequired,
    service: Annotated[LabOrderService, Depends(get_service)],
) -> LabOrderResponse:
    current_user.require("encounter:update")
    order = await service.create(current_user.org_id, payload, current_user.user_id)
    return LabOrderResponse.model_validate(order)


@router.get("/encounter/{encounter_id}", response_model=list[LabOrderResponse])
async def list_encounter_lab_orders(
    encounter_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[LabOrderService, Depends(get_service)],
) -> list[LabOrderResponse]:
    current_user.require("encounter:read")
    orders = await service.list_for_encounter(encounter_id, current_user.org_id)
    return [LabOrderResponse.model_validate(o) for o in orders]


@router.get("/patient/{patient_id}", response_model=list[LabOrderWithResultsResponse])
async def list_patient_lab_orders(
    patient_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[LabOrderService, Depends(get_service)],
) -> list[LabOrderWithResultsResponse]:
    current_user.require("encounter:read")
    orders = await service.list_for_patient(patient_id)
    return [LabOrderWithResultsResponse.model_validate(o) for o in orders]


@router.post("/{order_id}/results", response_model=LabOrderWithResultsResponse, status_code=201)
async def add_lab_results(
    order_id: uuid.UUID,
    payload: list[LabResultCreate],
    current_user: AuthRequired,
    service: Annotated[LabOrderService, Depends(get_service)],
) -> LabOrderWithResultsResponse:
    current_user.require("encounter:update")
    order = await service.add_result(order_id, current_user.org_id, payload)
    return LabOrderWithResultsResponse.model_validate(order)


@router.delete("/{order_id}", status_code=204)
async def cancel_lab_order(
    order_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[LabOrderService, Depends(get_service)],
) -> None:
    current_user.require("encounter:update")
    await service.cancel(order_id, current_user.org_id)
