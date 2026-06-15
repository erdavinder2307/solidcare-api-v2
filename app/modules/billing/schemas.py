import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.billing.invoices.models import InvoiceStatus, ServiceCategory
from app.modules.billing.payments.models import PaymentMethod, PaymentStatus


class LineItemCreate(BaseModel):
    service_category: ServiceCategory
    description: str
    quantity: float = 1.0
    unit_price: float
    discount_amount: float = 0.0
    tax_rate: float = Field(default=0.0, ge=0, le=100)


class LineItemResponse(BaseModel):
    id: uuid.UUID
    service_category: ServiceCategory
    description: str
    quantity: float
    unit_price: float
    discount_amount: float
    tax_rate: float
    tax_amount: float
    total_amount: float

    model_config = {"from_attributes": True}


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
    encounter_id: uuid.UUID | None
    notes: str | None
    line_items: list[LineItemResponse] = []

    model_config = {"from_attributes": True}


class InvoiceListItem(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    status: InvoiceStatus
    total_amount: float
    paid_amount: float
    outstanding_amount: float
    patient_id: uuid.UUID
    clinic_id: uuid.UUID

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    invoice_id: uuid.UUID
    patient_id: uuid.UUID
    clinic_id: uuid.UUID
    payment_method: PaymentMethod
    amount: float = Field(gt=0)
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


# ---------- Service Charge Master ----------

class ServiceChargeMasterCreate(BaseModel):
    clinic_id: uuid.UUID
    service_category: ServiceCategory
    service_code: str
    description: str
    standard_price: float = Field(gt=0)
    tax_rate: float = Field(default=0.0, ge=0, le=100)
    is_taxable: bool = False


class ServiceChargeMasterUpdate(BaseModel):
    description: str | None = None
    standard_price: float | None = Field(default=None, gt=0)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_taxable: bool | None = None
    is_active: bool | None = None


class ServiceChargeMasterResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    service_category: ServiceCategory
    service_code: str
    description: str
    standard_price: float
    tax_rate: float
    is_taxable: bool
    is_active: bool

    model_config = {"from_attributes": True}
