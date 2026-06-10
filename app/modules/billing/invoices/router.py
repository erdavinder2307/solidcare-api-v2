import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.billing.invoices.models import InvoiceStatus, ServiceCategory

router = APIRouter(prefix="/billing/invoices", tags=["Billing - Invoices"])


class LineItemCreate(BaseModel):
    service_category: ServiceCategory
    description: str
    quantity: float = 1.0
    unit_price: float
    discount_amount: float = 0.0
    tax_rate: float = 0.0


class InvoiceCreate(BaseModel):
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    invoice_date: date
    discount_percentage: float = Field(default=0.0, ge=0, le=100)
    notes: str | None = None
    line_items: list[LineItemCreate] = Field(min_length=1)


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    status: InvoiceStatus
    subtotal: float
    discount_amount: float
    taxable_amount: float
    cgst_amount: float
    sgst_amount: float
    total_tax: float
    total_amount: float
    paid_amount: float
    outstanding_amount: float
    patient_id: uuid.UUID
    clinic_id: uuid.UUID

    model_config = {"from_attributes": True}


@router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    payload: InvoiceCreate,
    current_user: AuthRequired,
) -> InvoiceResponse:
    current_user.require("billing:create")
    # Invoice creation logic with GST calculation
    return {"message": "Invoice created"}  # type: ignore


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: AuthRequired,
) -> InvoiceResponse:
    current_user.require("billing:read")
    return {"message": "Invoice detail"}  # type: ignore


@router.get("")
async def list_invoices(
    current_user: AuthRequired,
    clinic_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    current_user.require("billing:read")
    return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}
