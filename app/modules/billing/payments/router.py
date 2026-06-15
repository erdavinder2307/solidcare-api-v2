import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.billing.repository import InvoiceRepository, PaymentRepository
from app.modules.billing.schemas import PaymentCreate, PaymentResponse
from app.modules.billing.service import BillingService
from app.modules.patients.repository import PatientRepository

router = APIRouter(prefix="/billing/payments", tags=["Billing - Payments"])


def get_billing_service(session: Annotated[AsyncSession, Depends(get_db)]) -> BillingService:
    return BillingService(
        InvoiceRepository(session),
        PaymentRepository(session),
        PatientRepository(session),
    )


@router.post("", response_model=PaymentResponse, status_code=201)
async def record_payment(
    payload: PaymentCreate,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> PaymentResponse:
    current_user.require("billing:create")
    payment = await service.record_payment(current_user.org_id, payload, current_user.user_id)
    return PaymentResponse.model_validate(payment)


@router.get("/invoice/{invoice_id}", response_model=list[PaymentResponse])
async def get_invoice_payments(
    invoice_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> list[PaymentResponse]:
    current_user.require("billing:read")
    payments = await service.list_payments(invoice_id, current_user.org_id)
    return [PaymentResponse.model_validate(p) for p in payments]
