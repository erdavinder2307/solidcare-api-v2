import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.billing.payments.models import PaymentMethod, PaymentStatus

router = APIRouter(prefix="/billing/payments", tags=["Billing - Payments"])


class PaymentCreate(BaseModel):
    invoice_id: uuid.UUID
    patient_id: uuid.UUID
    clinic_id: uuid.UUID
    payment_method: PaymentMethod
    amount: float
    transaction_reference: str | None = None
    notes: str | None = None


class PaymentResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    payment_method: PaymentMethod
    status: PaymentStatus
    amount: float
    transaction_reference: str | None
    receipt_number: str | None
    paid_at: datetime | None

    model_config = {"from_attributes": True}


@router.post("", response_model=PaymentResponse, status_code=201)
async def record_payment(
    payload: PaymentCreate,
    current_user: AuthRequired,
) -> PaymentResponse:
    current_user.require("billing:create")
    return {"message": "Payment recorded"}  # type: ignore


@router.get("/invoice/{invoice_id}", response_model=list[PaymentResponse])
async def get_invoice_payments(
    invoice_id: uuid.UUID,
    current_user: AuthRequired,
) -> list[PaymentResponse]:
    current_user.require("billing:read")
    return []
