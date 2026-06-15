import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.billing.repository import InvoiceRepository, PaymentRepository
from app.modules.billing.schemas import (
    ServiceChargeMasterCreate,
    ServiceChargeMasterResponse,
    ServiceChargeMasterUpdate,
)
from app.modules.billing.service import BillingService
from app.modules.patients.repository import PatientRepository

router = APIRouter(prefix="/billing/service-charges", tags=["Billing - Service Charges"])


def get_billing_service(session: Annotated[AsyncSession, Depends(get_db)]) -> BillingService:
    return BillingService(
        InvoiceRepository(session),
        PaymentRepository(session),
        PatientRepository(session),
    )


@router.get("", response_model=list[ServiceChargeMasterResponse])
async def list_service_charges(
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
    clinic_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> list[ServiceChargeMasterResponse]:
    current_user.require("billing:read")
    items = await service.list_service_charges(current_user.org_id, clinic_id, active_only)
    return [ServiceChargeMasterResponse.model_validate(i) for i in items]


@router.post("", response_model=ServiceChargeMasterResponse, status_code=201)
async def create_service_charge(
    payload: ServiceChargeMasterCreate,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> ServiceChargeMasterResponse:
    current_user.require("billing:write")
    charge = await service.create_service_charge(current_user.org_id, payload)
    return ServiceChargeMasterResponse.model_validate(charge)


@router.patch("/{charge_id}", response_model=ServiceChargeMasterResponse)
async def update_service_charge(
    charge_id: uuid.UUID,
    payload: ServiceChargeMasterUpdate,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> ServiceChargeMasterResponse:
    current_user.require("billing:write")
    charge = await service.update_service_charge(charge_id, current_user.org_id, payload)
    return ServiceChargeMasterResponse.model_validate(charge)


@router.delete("/{charge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_charge(
    charge_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> None:
    current_user.require("billing:write")
    await service.delete_service_charge(charge_id, current_user.org_id)
