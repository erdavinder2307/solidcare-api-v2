import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.billing.invoices.models import Invoice, InvoiceStatus
from app.modules.billing.payments.models import Payment, PaymentStatus
from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import Encounter, EncounterStatus
from app.modules.patients.models import Patient


def _short_date_label(d: date) -> str:
    """Portable day + month label (strftime %-d is unsupported on Linux)."""
    return f"{d.day} {d.strftime('%b')}"


class ReportsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard_kpis(
        self, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None, report_date: date | None = None
    ) -> dict:
        target = report_date or date.today()
        start = datetime.combine(target, time.min, tzinfo=UTC)
        end = datetime.combine(target, time.max, tzinfo=UTC)

        appt_q = select(func.count(Appointment.id)).where(
            Appointment.organization_id == org_id,
            Appointment.appointment_date == target,
            Appointment.deleted_at.is_(None),
        )
        if clinic_id:
            appt_q = appt_q.where(Appointment.clinic_id == clinic_id)

        checked_in_q = appt_q.where(Appointment.status.in_([AppointmentStatus.CHECKED_IN, AppointmentStatus.IN_CONSULTATION]))
        _completed_appt_q = appt_q.where(Appointment.status == AppointmentStatus.COMPLETED)

        enc_q = select(func.count(Encounter.id)).where(
            Encounter.organization_id == org_id,
            Encounter.encounter_date >= start,
            Encounter.encounter_date <= end,
            Encounter.status == EncounterStatus.COMPLETED,
            Encounter.deleted_at.is_(None),
        )
        if clinic_id:
            enc_q = enc_q.where(Encounter.clinic_id == clinic_id)

        patient_q = select(func.count(Patient.id)).where(
            Patient.organization_id == org_id,
            Patient.created_at >= start,
            Patient.created_at <= end,
            Patient.deleted_at.is_(None),
        )

        revenue_q = select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
            Payment.organization_id == org_id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.paid_at >= start,
            Payment.paid_at <= end,
            Payment.deleted_at.is_(None),
        )
        if clinic_id:
            revenue_q = revenue_q.where(Payment.clinic_id == clinic_id)

        pending_q = select(func.count(Invoice.id)).where(
            Invoice.organization_id == org_id,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
            Invoice.deleted_at.is_(None),
        )
        if clinic_id:
            pending_q = pending_q.where(Invoice.clinic_id == clinic_id)

        today_appointments = (await self.session.execute(appt_q)).scalar_one() or 0
        checked_in = (await self.session.execute(checked_in_q)).scalar_one() or 0
        completed_consultations = (await self.session.execute(enc_q)).scalar_one() or 0
        new_patients = (await self.session.execute(patient_q)).scalar_one() or 0
        today_revenue = float((await self.session.execute(revenue_q)).scalar_one() or 0)
        pending_bills = (await self.session.execute(pending_q)).scalar_one() or 0

        return {
            "today_appointments": today_appointments,
            "today_revenue": round(today_revenue, 2),
            "new_patients_today": new_patients,
            "pending_bills": pending_bills,
            "checked_in_patients": checked_in,
            "completed_consultations": completed_consultations,
        }

    async def daily_opd(self, org_id: uuid.UUID, clinic_id: uuid.UUID, report_date: date) -> dict:
        result = await self.session.execute(
            select(Appointment).where(
                Appointment.organization_id == org_id,
                Appointment.clinic_id == clinic_id,
                Appointment.appointment_date == report_date,
                Appointment.deleted_at.is_(None),
            )
        )
        appointments = list(result.scalars().all())
        return {
            "date": str(report_date),
            "clinic_id": str(clinic_id),
            "total_appointments": len(appointments),
            "completed": sum(1 for a in appointments if a.status == AppointmentStatus.COMPLETED),
            "cancelled": sum(1 for a in appointments if a.status == AppointmentStatus.CANCELLED),
            "no_show": sum(1 for a in appointments if a.status == AppointmentStatus.NO_SHOW),
            "doctor_wise": [],
        }

    async def revenue_report(
        self, org_id: uuid.UUID, from_date: date, to_date: date, clinic_id: uuid.UUID | None = None
    ) -> dict:
        inv_q = select(
            func.coalesce(func.sum(Invoice.total_amount), 0.0),
            func.coalesce(func.sum(Invoice.paid_amount), 0.0),
            func.coalesce(func.sum(Invoice.outstanding_amount), 0.0),
        ).where(
            Invoice.organization_id == org_id,
            Invoice.invoice_date >= from_date,
            Invoice.invoice_date <= to_date,
            Invoice.deleted_at.is_(None),
        )
        if clinic_id:
            inv_q = inv_q.where(Invoice.clinic_id == clinic_id)
        totals = (await self.session.execute(inv_q)).one()
        return {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "total_revenue": float(totals[0]),
            "total_collected": float(totals[1]),
            "outstanding": float(totals[2]),
            "payment_method_breakdown": {},
            "daily_breakdown": [],
        }

    async def patient_demographics(
        self, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None
    ) -> dict:
        total_q = select(func.count(Patient.id)).where(
            Patient.organization_id == org_id, Patient.deleted_at.is_(None)
        )
        total = (await self.session.execute(total_q)).scalar_one() or 0
        return {
            "total_patients": total,
            "new_patients": 0,
            "gender_distribution": {},
            "age_distribution": {},
            "city_distribution": {},
        }

    async def appointments_trend(
        self,
        org_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        days: int = 30,
    ) -> list[dict]:
        """Return daily appointment count for the last `days` days."""
        from datetime import timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        q = (
            select(
                Appointment.appointment_date,
                func.count(Appointment.id).label("total"),
                func.count(Appointment.id)
                .filter(Appointment.status == AppointmentStatus.COMPLETED)
                .label("completed"),
            )
            .where(
                Appointment.organization_id == org_id,
                Appointment.appointment_date >= start_date,
                Appointment.appointment_date <= end_date,
                Appointment.deleted_at.is_(None),
            )
            .group_by(Appointment.appointment_date)
            .order_by(Appointment.appointment_date)
        )
        if clinic_id:
            q = q.where(Appointment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        row_map = {str(r.appointment_date): {"total": r.total, "completed": r.completed} for r in rows}

        result = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            key = str(d)
            result.append({
                "date": key,
                "label": _short_date_label(d),
                "total": row_map.get(key, {}).get("total", 0),
                "completed": row_map.get(key, {}).get("completed", 0),
            })
        return result

    async def revenue_trend(
        self,
        org_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        weeks: int = 8,
    ) -> list[dict]:
        """Return weekly collected revenue for the last `weeks` weeks."""
        from datetime import timedelta
        today = date.today()
        # Align to Monday of current week
        week_start = today - timedelta(days=today.weekday())
        start = week_start - timedelta(weeks=weeks - 1)

        q = (
            select(
                func.date_trunc("week", Payment.paid_at).label("week_start"),
                func.coalesce(func.sum(Payment.amount), 0.0).label("revenue"),
            )
            .where(
                Payment.organization_id == org_id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= datetime.combine(start, time.min, tzinfo=UTC),
                Payment.deleted_at.is_(None),
            )
            .group_by(func.date_trunc("week", Payment.paid_at))
            .order_by(func.date_trunc("week", Payment.paid_at))
        )
        if clinic_id:
            q = q.where(Payment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        row_map = {r.week_start.date(): float(r.revenue) for r in rows}

        result = []
        for i in range(weeks):
            ws = start + timedelta(weeks=i)
            result.append({
                "week": str(ws),
                "label": _short_date_label(ws),
                "revenue": row_map.get(ws, 0.0),
            })
        return result

    async def appointment_type_distribution(
        self, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None, days: int = 30
    ) -> list[dict]:
        """Return appointment type breakdown for the last `days` days."""
        from datetime import timedelta
        since = date.today() - timedelta(days=days)

        q = (
            select(
                Appointment.appointment_type,
                func.count(Appointment.id).label("count"),
            )
            .where(
                Appointment.organization_id == org_id,
                Appointment.appointment_date >= since,
                Appointment.deleted_at.is_(None),
            )
            .group_by(Appointment.appointment_type)
        )
        if clinic_id:
            q = q.where(Appointment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        return [{"type": r.appointment_type, "count": r.count} for r in rows]

    async def top_diagnoses(
        self,
        org_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        days: int = 30,
        limit: int = 10,
    ) -> list[dict]:
        """Return top `limit` diagnoses by frequency over the last `days` days."""
        from datetime import timedelta
        since = date.today() - timedelta(days=days)

        q = (
            select(
                func.coalesce(Diagnosis.icd10_code, Diagnosis.custom_description, "Unknown").label("code"),
                func.coalesce(Diagnosis.icd10_description, Diagnosis.custom_description, "Unknown").label("description"),
                func.count(Diagnosis.id).label("count"),
            )
            .join(Encounter, Encounter.id == Diagnosis.encounter_id)
            .where(
                Encounter.organization_id == org_id,
                Encounter.encounter_date >= datetime.combine(since, time.min, tzinfo=UTC),
                Diagnosis.deleted_at.is_(None),
                Encounter.deleted_at.is_(None),
            )
            .group_by(
                func.coalesce(Diagnosis.icd10_code, Diagnosis.custom_description, "Unknown"),
                func.coalesce(Diagnosis.icd10_description, Diagnosis.custom_description, "Unknown"),
            )
            .order_by(func.count(Diagnosis.id).desc())
            .limit(limit)
        )
        if clinic_id:
            q = q.where(Encounter.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        return [{"code": r.code, "description": r.description, "count": r.count} for r in rows]

    async def opd_volume_trend(
        self,
        org_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict]:
        """Return daily appointment count between two dates (default last 30 days)."""
        from datetime import timedelta
        end = to_date or date.today()
        start = from_date or (end - timedelta(days=29))
        days = (end - start).days + 1

        q = (
            select(
                Appointment.appointment_date,
                func.count(Appointment.id).label("total"),
                func.count(Appointment.id)
                .filter(Appointment.status == AppointmentStatus.COMPLETED)
                .label("completed"),
            )
            .where(
                Appointment.organization_id == org_id,
                Appointment.appointment_date >= start,
                Appointment.appointment_date <= end,
                Appointment.deleted_at.is_(None),
            )
            .group_by(Appointment.appointment_date)
            .order_by(Appointment.appointment_date)
        )
        if clinic_id:
            q = q.where(Appointment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        row_map = {str(r.appointment_date): {"total": r.total, "completed": r.completed} for r in rows}

        result = []
        for i in range(days):
            d = start + timedelta(days=i)
            key = str(d)
            result.append({
                "date": key,
                "label": _short_date_label(d),
                "total": row_map.get(key, {}).get("total", 0),
                "completed": row_map.get(key, {}).get("completed", 0),
            })
        return result
