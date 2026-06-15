import uuid
from datetime import date, datetime, timezone

from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.billing.invoices.models import Invoice, InvoiceLineItem, InvoiceStatus, ServiceChargeMaster
from app.modules.billing.payments.models import Payment, PaymentMethod, PaymentStatus
from app.modules.billing.repository import InvoiceRepository, PaymentRepository
from app.modules.billing.schemas import InvoiceCreate, PaymentCreate, ServiceChargeMasterCreate, ServiceChargeMasterUpdate
from app.modules.patients.repository import PatientRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams
from sqlalchemy import select


class BillingService:
    def __init__(
        self,
        invoice_repo: InvoiceRepository,
        payment_repo: PaymentRepository,
        patient_repo: PatientRepository,
    ) -> None:
        self.invoice_repo = invoice_repo
        self.payment_repo = payment_repo
        self.patient_repo = patient_repo

    async def create_invoice(
        self, org_id: uuid.UUID, data: InvoiceCreate, created_by: uuid.UUID
    ) -> Invoice:
        patient = await self.patient_repo.get_by_id(data.patient_id, org_id)
        if not patient:
            raise NotFoundError("Patient", str(data.patient_id))

        line_items: list[InvoiceLineItem] = []
        subtotal = 0.0
        total_tax = 0.0

        for item_data in data.line_items:
            line_subtotal = (item_data.quantity * item_data.unit_price) - item_data.discount_amount
            line_subtotal = max(line_subtotal, 0.0)
            tax_amount = round(line_subtotal * item_data.tax_rate / 100, 2)
            total_amount = round(line_subtotal + tax_amount, 2)
            subtotal += line_subtotal
            total_tax += tax_amount
            line_items.append(
                InvoiceLineItem(
                    service_category=item_data.service_category,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    discount_amount=item_data.discount_amount,
                    tax_rate=item_data.tax_rate,
                    tax_amount=tax_amount,
                    total_amount=total_amount,
                )
            )

        subtotal = round(subtotal, 2)
        discount_amount = round(subtotal * data.discount_percentage / 100, 2)
        taxable_amount = round(subtotal - discount_amount, 2)
        adjusted_tax = round(total_tax * (taxable_amount / subtotal), 2) if subtotal else 0.0
        cgst_amount = round(adjusted_tax / 2, 2)
        sgst_amount = round(adjusted_tax / 2, 2)
        total_amount = round(taxable_amount + adjusted_tax, 2)

        invoice_number = await self.invoice_repo.next_invoice_number(org_id, data.invoice_date)
        invoice = Invoice(
            organization_id=org_id,
            clinic_id=data.clinic_id,
            patient_id=data.patient_id,
            encounter_id=data.encounter_id,
            invoice_number=invoice_number,
            invoice_date=data.invoice_date,
            status=InvoiceStatus.ISSUED,
            subtotal=subtotal,
            discount_amount=discount_amount,
            discount_percentage=data.discount_percentage,
            taxable_amount=taxable_amount,
            cgst_rate=9.0 if adjusted_tax else 0.0,
            sgst_rate=9.0 if adjusted_tax else 0.0,
            cgst_amount=cgst_amount,
            sgst_amount=sgst_amount,
            total_tax=adjusted_tax,
            total_amount=total_amount,
            paid_amount=0.0,
            outstanding_amount=total_amount,
            notes=data.notes,
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        saved_invoice = await self.invoice_repo.create(invoice, line_items)
        await self._generate_invoice_pdf(saved_invoice)
        return saved_invoice

    async def _generate_invoice_pdf(self, invoice: Invoice) -> None:
        """Generate PDF for an invoice and upload to Blob Storage. Non-blocking on failure."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from sqlalchemy import select
            from app.shared.services.pdf_service import (
                ClinicInfo, PatientInfo, InvoiceLineItem as PdfLineItem,
                generate_invoice_pdf,
            )
            from app.modules.clinics.models import Clinic
            from app.modules.patients.models import Patient

            session = self.invoice_repo.session
            clinic_row = (await session.execute(
                select(Clinic).where(Clinic.id == invoice.clinic_id)
            )).scalar_one_or_none()
            patient_row = (await session.execute(
                select(Patient).where(Patient.id == invoice.patient_id)
            )).scalar_one_or_none()

            clinic_info = ClinicInfo(
                name=clinic_row.name if clinic_row else "SolidCare Clinic",
                address=", ".join(filter(None, [
                    getattr(clinic_row, "address_line1", None),
                    getattr(clinic_row, "city", None),
                    getattr(clinic_row, "state", None),
                ])) if clinic_row else "",
                phone=getattr(clinic_row, "phone", "") or "",
                email=getattr(clinic_row, "email", "") or "",
                registration_number=getattr(clinic_row, "registration_number", None),
                gstin=getattr(clinic_row, "gstin", None),
            )
            patient_info = PatientInfo(
                full_name=patient_row.full_name if patient_row else "Unknown",
                patient_id=str(invoice.patient_id),
                dob=str(patient_row.date_of_birth) if patient_row and patient_row.date_of_birth else None,
                phone=getattr(patient_row, "phone", None),
                address=getattr(patient_row, "address_line1", None),
            )
            pdf_items = [
                PdfLineItem(
                    description=li.description,
                    quantity=li.quantity,
                    unit_price=li.unit_price,
                    discount_amount=li.discount_amount,
                    total_amount=li.total_amount,
                    tax_rate=li.tax_rate,
                )
                for li in invoice.line_items
            ]
            pdf_bytes = generate_invoice_pdf(
                clinic=clinic_info,
                patient=patient_info,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                line_items=pdf_items,
                subtotal=invoice.subtotal,
                discount_amount=invoice.discount_amount,
                cgst_amount=invoice.cgst_amount,
                sgst_amount=invoice.sgst_amount,
                igst_amount=0.0,
                total_amount=invoice.total_amount,
                paid_amount=invoice.paid_amount,
                outstanding_amount=invoice.outstanding_amount,
                notes=invoice.notes,
            )
            blob_name = f"invoices/{invoice.id}.pdf"
            try:
                from app.core.storage.blob_service import upload_bytes
                await upload_bytes(pdf_bytes, blob_name, "application/pdf")
            except RuntimeError:
                pass  # Azure Storage not configured — skip upload
            invoice.pdf_path = blob_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("Invoice PDF generation failed for %s: %s", invoice.id, exc)


        invoice = await self.invoice_repo.get_by_id(invoice_id, org_id)
        if not invoice:
            raise NotFoundError("Invoice", str(invoice_id))
        return invoice

    async def list_invoices(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        **filters,
    ) -> PaginatedResponse:
        items, total = await self.invoice_repo.list(org_id, params, **filters)
        return PaginatedResponse.create(items, total, params)

    async def record_payment(
        self, org_id: uuid.UUID, data: PaymentCreate, created_by: uuid.UUID
    ) -> Payment:
        invoice = await self.get_invoice(data.invoice_id, org_id)
        if invoice.patient_id != data.patient_id:
            raise BusinessRuleError("Patient does not match invoice")
        if invoice.status in (InvoiceStatus.CANCELLED, InvoiceStatus.PAID):
            raise BusinessRuleError(f"Cannot pay invoice with status {invoice.status.value}")
        if data.amount > invoice.outstanding_amount + 0.01:
            raise BusinessRuleError("Payment amount exceeds outstanding balance")

        receipt_number = await self.payment_repo.next_receipt_number(org_id)
        payment = Payment(
            organization_id=org_id,
            clinic_id=data.clinic_id,
            invoice_id=data.invoice_id,
            patient_id=data.patient_id,
            payment_method=data.payment_method,
            status=PaymentStatus.COMPLETED,
            amount=round(data.amount, 2),
            transaction_reference=data.transaction_reference,
            notes=data.notes,
            receipt_number=receipt_number,
            paid_at=datetime.now(timezone.utc),
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        payment = await self.payment_repo.create(payment)

        invoice.paid_amount = round(invoice.paid_amount + payment.amount, 2)
        invoice.outstanding_amount = round(max(invoice.total_amount - invoice.paid_amount, 0.0), 2)
        if invoice.outstanding_amount <= 0:
            invoice.status = InvoiceStatus.PAID
        elif invoice.paid_amount > 0:
            invoice.status = InvoiceStatus.PARTIALLY_PAID

        return payment

    async def list_payments(self, invoice_id: uuid.UUID, org_id: uuid.UUID) -> list[Payment]:
        await self.get_invoice(invoice_id, org_id)
        return await self.payment_repo.list_for_invoice(invoice_id, org_id)

    async def cancel_invoice(self, invoice_id: uuid.UUID, org_id: uuid.UUID, reason: str | None = None) -> Invoice:
        invoice = await self.get_invoice(invoice_id, org_id)
        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED):
            raise BusinessRuleError(f"Cannot cancel invoice with status {invoice.status.value}")
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancellation_reason = reason
        invoice.cancelled_at = datetime.now(timezone.utc)
        invoice.outstanding_amount = 0.0
        return invoice

    # ---------- Service Charge Master ----------

    async def list_service_charges(
        self, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None, active_only: bool = True
    ) -> list[ServiceChargeMaster]:
        q = select(ServiceChargeMaster).join(
            Invoice.__table__.c.clinic_id if False else ServiceChargeMaster
        )
        # Build query manually — join to clinic → organization
        from app.modules.clinics.models import Clinic
        q = (
            select(ServiceChargeMaster)
            .join(Clinic, Clinic.id == ServiceChargeMaster.clinic_id)
            .where(Clinic.organization_id == org_id)
        )
        if clinic_id:
            q = q.where(ServiceChargeMaster.clinic_id == clinic_id)
        if active_only:
            q = q.where(ServiceChargeMaster.is_active.is_(True))
        q = q.where(ServiceChargeMaster.deleted_at.is_(None)).order_by(
            ServiceChargeMaster.service_category, ServiceChargeMaster.description
        )
        result = await self.invoice_repo.session.execute(q)
        return list(result.scalars().all())

    async def create_service_charge(
        self, org_id: uuid.UUID, data: ServiceChargeMasterCreate
    ) -> ServiceChargeMaster:
        from app.modules.clinics.models import Clinic
        clinic = (await self.invoice_repo.session.execute(
            select(Clinic).where(Clinic.id == data.clinic_id, Clinic.organization_id == org_id)
        )).scalar_one_or_none()
        if not clinic:
            raise NotFoundError("Clinic", str(data.clinic_id))
        charge = ServiceChargeMaster(**data.model_dump())
        self.invoice_repo.session.add(charge)
        await self.invoice_repo.session.flush()
        return charge

    async def update_service_charge(
        self, charge_id: uuid.UUID, org_id: uuid.UUID, data: ServiceChargeMasterUpdate
    ) -> ServiceChargeMaster:
        charge = await self._get_service_charge(charge_id, org_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(charge, field, value)
        return charge

    async def delete_service_charge(self, charge_id: uuid.UUID, org_id: uuid.UUID) -> None:
        charge = await self._get_service_charge(charge_id, org_id)
        from datetime import timezone as tz
        charge.deleted_at = datetime.now(tz.utc)

    async def _get_service_charge(self, charge_id: uuid.UUID, org_id: uuid.UUID) -> ServiceChargeMaster:
        from app.modules.clinics.models import Clinic
        result = await self.invoice_repo.session.execute(
            select(ServiceChargeMaster)
            .join(Clinic, Clinic.id == ServiceChargeMaster.clinic_id)
            .where(
                ServiceChargeMaster.id == charge_id,
                Clinic.organization_id == org_id,
                ServiceChargeMaster.deleted_at.is_(None),
            )
        )
        charge = result.scalar_one_or_none()
        if not charge:
            raise NotFoundError("ServiceChargeMaster", str(charge_id))
        return charge
        invoice = await self.get_invoice(invoice_id, org_id)
        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED):
            raise BusinessRuleError(f"Cannot cancel invoice with status {invoice.status.value}")
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancellation_reason = reason
        invoice.cancelled_at = datetime.now(timezone.utc)
        invoice.outstanding_amount = 0.0
        return invoice
