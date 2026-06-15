import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.billing.invoices.models import InvoiceStatus
from app.modules.billing.repository import InvoiceRepository, PaymentRepository
from app.modules.billing.schemas import InvoiceCreate, InvoiceListItem, InvoiceResponse
from app.modules.billing.service import BillingService
from app.modules.patients.repository import PatientRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/billing/invoices", tags=["Billing - Invoices"])


def get_billing_service(session: Annotated[AsyncSession, Depends(get_db)]) -> BillingService:
    return BillingService(
        InvoiceRepository(session),
        PaymentRepository(session),
        PatientRepository(session),
    )


@router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    payload: InvoiceCreate,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> InvoiceResponse:
    current_user.require("billing:create")
    invoice = await service.create_invoice(current_user.org_id, payload, current_user.user_id)
    return InvoiceResponse.model_validate(invoice)


@router.get("", response_model=PaginatedResponse[InvoiceListItem])
async def list_invoices(
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
    clinic_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse:
    current_user.require("billing:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list_invoices(
        current_user.org_id,
        params,
        clinic_id=clinic_id,
        patient_id=patient_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> InvoiceResponse:
    current_user.require("billing:read")
    invoice = await service.get_invoice(invoice_id, current_user.org_id)
    return InvoiceResponse.model_validate(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[BillingService, Depends(get_billing_service)],
    reason: str | None = None,
) -> InvoiceResponse:
    current_user.require("billing:create")
    invoice = await service.cancel_invoice(invoice_id, current_user.org_id, reason)
    return InvoiceResponse.model_validate(invoice)
