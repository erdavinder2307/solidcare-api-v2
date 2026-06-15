import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.billing.invoices.models import Invoice, InvoiceLineItem, InvoiceStatus
from app.modules.billing.payments.models import Payment
from app.shared.schemas.pagination import PaginationParams
from app.shared.utils.pagination import paginate


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, invoice: Invoice, line_items: list[InvoiceLineItem]) -> Invoice:
        self.session.add(invoice)
        await self.session.flush()
        for idx, item in enumerate(line_items):
            item.invoice_id = invoice.id
            item.sort_order = idx
            self.session.add(item)
        await self.session.flush()
        return await self.get_by_id(invoice.id, invoice.organization_id)

    async def get_by_id(self, invoice_id: uuid.UUID, org_id: uuid.UUID) -> Invoice | None:
        result = await self.session.execute(
            select(Invoice)
            .where(
                Invoice.id == invoice_id,
                Invoice.organization_id == org_id,
                Invoice.deleted_at.is_(None),
            )
            .options(selectinload(Invoice.line_items), selectinload(Invoice.payments))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        clinic_id: uuid.UUID | None = None,
        patient_id: uuid.UUID | None = None,
        status: InvoiceStatus | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[Invoice], int]:
        query = (
            select(Invoice)
            .where(Invoice.organization_id == org_id, Invoice.deleted_at.is_(None))
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        )
        if clinic_id:
            query = query.where(Invoice.clinic_id == clinic_id)
        if patient_id:
            query = query.where(Invoice.patient_id == patient_id)
        if status:
            query = query.where(Invoice.status == status)
        if from_date:
            query = query.where(Invoice.invoice_date >= from_date)
        if to_date:
            query = query.where(Invoice.invoice_date <= to_date)
        return await paginate(self.session, query, params)

    async def next_invoice_number(self, org_id: uuid.UUID, invoice_date: date) -> str:
        prefix = f"INV-{invoice_date.year}"
        result = await self.session.execute(
            select(func.count(Invoice.id)).where(
                Invoice.organization_id == org_id,
                Invoice.invoice_number.like(f"{prefix}-%"),
            )
        )
        count = result.scalar_one_or_none() or 0
        return f"{prefix}-{count + 1:05d}"


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def list_for_invoice(self, invoice_id: uuid.UUID, org_id: uuid.UUID) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(
                Payment.invoice_id == invoice_id,
                Payment.organization_id == org_id,
                Payment.deleted_at.is_(None),
            )
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def next_receipt_number(self, org_id: uuid.UUID) -> str:
        result = await self.session.execute(
            select(func.count(Payment.id)).where(Payment.organization_id == org_id)
        )
        count = result.scalar_one_or_none() or 0
        return f"RCP-{count + 1:06d}"
