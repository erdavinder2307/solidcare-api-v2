import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.billing.invoices.models import Invoice, InvoiceStatus
from app.modules.billing.payments.models import REVENUE_STATUSES, Payment
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
            Payment.status.in_(REVENUE_STATUSES),
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

        doctor_wise: dict[str, dict] = {}
        for a in appointments:
            key = str(a.doctor_id)
            bucket = doctor_wise.setdefault(
                key, {"doctor_id": key, "total": 0, "completed": 0, "cancelled": 0, "no_show": 0}
            )
            bucket["total"] += 1
            if a.status == AppointmentStatus.COMPLETED:
                bucket["completed"] += 1
            elif a.status == AppointmentStatus.CANCELLED:
                bucket["cancelled"] += 1
            elif a.status == AppointmentStatus.NO_SHOW:
                bucket["no_show"] += 1

        return {
            "date": str(report_date),
            "clinic_id": str(clinic_id),
            "total_appointments": len(appointments),
            "completed": sum(1 for a in appointments if a.status == AppointmentStatus.COMPLETED),
            "cancelled": sum(1 for a in appointments if a.status == AppointmentStatus.CANCELLED),
            "no_show": sum(1 for a in appointments if a.status == AppointmentStatus.NO_SHOW),
            "doctor_wise": sorted(doctor_wise.values(), key=lambda d: d["total"], reverse=True),
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

    async def doctor_summary(
        self,
        org_id: uuid.UUID,
        doctor_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> dict:
        """Per-doctor performance: appointments, consultations, patients, revenue, and a daily trend."""
        from datetime import timedelta

        start_dt = datetime.combine(from_date, time.min, tzinfo=UTC)
        end_dt = datetime.combine(to_date, time.max, tzinfo=UTC)

        # Appointments (total + completed) in range
        appt_q = select(
            func.count(Appointment.id),
            func.count(Appointment.id).filter(Appointment.status == AppointmentStatus.COMPLETED),
        ).where(
            Appointment.organization_id == org_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date >= from_date,
            Appointment.appointment_date <= to_date,
            Appointment.deleted_at.is_(None),
        )
        appt_total, appt_completed = (await self.session.execute(appt_q)).one()

        # Completed consultations (encounters) + unique patients
        enc_filters = [
            Encounter.organization_id == org_id,
            Encounter.doctor_id == doctor_id,
            Encounter.status == EncounterStatus.COMPLETED,
            Encounter.encounter_date >= start_dt,
            Encounter.encounter_date <= end_dt,
            Encounter.deleted_at.is_(None),
        ]
        consultations = (
            await self.session.execute(select(func.count(Encounter.id)).where(*enc_filters))
        ).scalar_one() or 0
        unique_patients = (
            await self.session.execute(
                select(func.count(func.distinct(Encounter.patient_id))).where(*enc_filters)
            )
        ).scalar_one() or 0

        # Revenue: completed payments on invoices tied to this doctor's encounters
        revenue_q = (
            select(func.coalesce(func.sum(Payment.amount), 0.0))
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Encounter, Encounter.id == Invoice.encounter_id)
            .where(
                Payment.organization_id == org_id,
                Payment.status.in_(REVENUE_STATUSES),
                Encounter.doctor_id == doctor_id,
                Payment.paid_at >= start_dt,
                Payment.paid_at <= end_dt,
                Payment.deleted_at.is_(None),
            )
        )
        revenue = float((await self.session.execute(revenue_q)).scalar_one() or 0)

        # Daily consultation trend
        trend_q = (
            select(
                func.date(Encounter.encounter_date).label("day"),
                func.count(Encounter.id).label("count"),
            )
            .where(*enc_filters)
            .group_by(func.date(Encounter.encounter_date))
            .order_by(func.date(Encounter.encounter_date))
        )
        trend_rows = (await self.session.execute(trend_q)).all()
        trend_map = {str(r.day): r.count for r in trend_rows}
        days = (to_date - from_date).days + 1
        daily_trend = []
        for i in range(days):
            d = from_date + timedelta(days=i)
            daily_trend.append({
                "date": str(d),
                "label": _short_date_label(d),
                "consultations": trend_map.get(str(d), 0),
            })

        return {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "appointments_total": appt_total or 0,
            "appointments_completed": appt_completed or 0,
            "consultations": consultations,
            "unique_patients": unique_patients,
            "revenue_generated": round(revenue, 2),
            "daily_trend": daily_trend,
        }

    async def doctor_collection(
        self,
        org_id: uuid.UUID,
        from_date: date,
        to_date: date,
        clinic_id: uuid.UUID | None = None,
    ) -> dict:
        """Revenue collected per doctor, attributed via encounter → invoice → payment."""
        start = datetime.combine(from_date, time.min, tzinfo=UTC)
        end = datetime.combine(to_date, time.max, tzinfo=UTC)

        q = (
            select(
                Encounter.doctor_id,
                func.coalesce(func.sum(Payment.amount), 0.0).label("collected"),
                func.count(func.distinct(Invoice.id)).label("invoices"),
            )
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Encounter, Encounter.id == Invoice.encounter_id)
            .where(
                Payment.organization_id == org_id,
                Payment.status.in_(REVENUE_STATUSES),
                Payment.paid_at >= start,
                Payment.paid_at <= end,
                Payment.deleted_at.is_(None),
            )
            .group_by(Encounter.doctor_id)
            .order_by(func.coalesce(func.sum(Payment.amount), 0.0).desc())
        )
        if clinic_id:
            q = q.where(Payment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        return {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "doctors": [
                {
                    "doctor_id": str(r.doctor_id),
                    "collected": round(float(r.collected), 2),
                    "invoices": r.invoices,
                }
                for r in rows
            ],
        }

    async def outstanding_aging(
        self,
        org_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        as_of: date | None = None,
    ) -> dict:
        """Outstanding receivables aged into 0-30 / 31-60 / 61-90 / 90+ buckets.

        Aging is measured in days from each invoice's `invoice_date` to `as_of`
        (default today). Only invoices that still carry a positive
        `outstanding_amount` and are issued or partially paid are included.
        """
        reference = as_of or date.today()

        q = (
            select(
                Invoice.id,
                Invoice.invoice_number,
                Invoice.invoice_date,
                Invoice.due_date,
                Invoice.outstanding_amount,
                Patient.first_name,
                Patient.last_name,
                Patient.phone,
            )
            .join(Patient, Patient.id == Invoice.patient_id)
            .where(
                Invoice.organization_id == org_id,
                Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
                Invoice.outstanding_amount > 0,
                Invoice.deleted_at.is_(None),
            )
            .order_by(Invoice.invoice_date)
        )
        if clinic_id:
            q = q.where(Invoice.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()

        buckets = {
            "current": {"label": "0-30 days", "count": 0, "amount": 0.0},
            "days_31_60": {"label": "31-60 days", "count": 0, "amount": 0.0},
            "days_61_90": {"label": "61-90 days", "count": 0, "amount": 0.0},
            "over_90": {"label": "90+ days", "count": 0, "amount": 0.0},
        }
        invoices = []
        total = 0.0

        for r in rows:
            age = (reference - r.invoice_date).days
            if age <= 30:
                key = "current"
            elif age <= 60:
                key = "days_31_60"
            elif age <= 90:
                key = "days_61_90"
            else:
                key = "over_90"

            amount = float(r.outstanding_amount or 0.0)
            buckets[key]["count"] += 1
            buckets[key]["amount"] = round(buckets[key]["amount"] + amount, 2)
            total = round(total + amount, 2)

            invoices.append({
                "invoice_id": str(r.id),
                "invoice_number": r.invoice_number,
                "invoice_date": str(r.invoice_date),
                "due_date": str(r.due_date) if r.due_date else None,
                "patient_name": f"{r.first_name} {r.last_name}",
                "patient_phone": r.phone,
                "outstanding_amount": round(amount, 2),
                "days_overdue": age,
                "bucket": key,
            })

        return {
            "as_of": str(reference),
            "total_outstanding": total,
            "total_invoices": len(invoices),
            "buckets": [
                {"key": k, **v} for k, v in buckets.items()
            ],
            "invoices": invoices,
        }

    async def patient_demographics(
        self, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None
    ) -> dict:
        from datetime import timedelta

        base = [Patient.organization_id == org_id, Patient.deleted_at.is_(None)]

        total = (
            await self.session.execute(select(func.count(Patient.id)).where(*base))
        ).scalar_one() or 0

        # Registered in the last 30 days
        since = datetime.combine(date.today() - timedelta(days=30), time.min, tzinfo=UTC)
        new_patients = (
            await self.session.execute(
                select(func.count(Patient.id)).where(*base, Patient.created_at >= since)
            )
        ).scalar_one() or 0

        gender_rows = (
            await self.session.execute(
                select(Patient.gender, func.count(Patient.id))
                .where(*base)
                .group_by(Patient.gender)
            )
        ).all()
        gender_distribution = {(g or "unknown").lower(): c for g, c in gender_rows}

        city_rows = (
            await self.session.execute(
                select(Patient.city, func.count(Patient.id).label("n"))
                .where(*base, Patient.city.isnot(None))
                .group_by(Patient.city)
                .order_by(func.count(Patient.id).desc())
                .limit(10)
            )
        ).all()
        city_distribution = {c: n for c, n in city_rows}

        # Age bands derived from date_of_birth
        age_years = func.date_part("year", func.age(Patient.date_of_birth))
        band = case(
            (age_years < 18, "0-17"),
            (age_years < 31, "18-30"),
            (age_years < 46, "31-45"),
            (age_years < 61, "46-60"),
            else_="60+",
        )
        age_rows = (
            await self.session.execute(
                select(band.label("band"), func.count(Patient.id))
                .where(*base, Patient.date_of_birth.isnot(None))
                .group_by(band)
            )
        ).all()
        age_distribution = {b: c for b, c in age_rows}

        return {
            "total_patients": total,
            "new_patients": new_patients,
            "gender_distribution": gender_distribution,
            "age_distribution": age_distribution,
            "city_distribution": city_distribution,
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

        # Truncate in UTC. Applying date_trunc directly to a timestamptz uses the
        # DB session timezone, so a non-UTC server returns Monday-00:00-local —
        # which reads back as the *previous* day in UTC and never matches the
        # Monday keys generated below, zeroing out every bucket.
        week_bucket = func.date_trunc("week", func.timezone("UTC", Payment.paid_at))

        q = (
            select(
                week_bucket.label("week_start"),
                func.coalesce(func.sum(Payment.amount), 0.0).label("revenue"),
            )
            .where(
                Payment.organization_id == org_id,
                Payment.status.in_(REVENUE_STATUSES),
                Payment.paid_at >= datetime.combine(start, time.min, tzinfo=UTC),
                Payment.deleted_at.is_(None),
            )
            .group_by(week_bucket)
            .order_by(week_bucket)
        )
        if clinic_id:
            q = q.where(Payment.clinic_id == clinic_id)

        rows = (await self.session.execute(q)).all()
        row_map = {}
        for r in rows:
            ws = r.week_start.date() if hasattr(r.week_start, "date") else r.week_start
            row_map[ws] = float(r.revenue)

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

        # Reuse the same expression objects in SELECT and GROUP BY — building them
        # twice emits distinct bind params, which Postgres rejects as un-grouped columns.
        code_expr = func.coalesce(Diagnosis.icd10_code, Diagnosis.custom_description, "Unknown")
        description_expr = func.coalesce(
            Diagnosis.icd10_description, Diagnosis.custom_description, "Unknown"
        )

        q = (
            select(
                code_expr.label("code"),
                description_expr.label("description"),
                func.count(Diagnosis.id).label("count"),
            )
            .join(Encounter, Encounter.id == Diagnosis.encounter_id)
            .where(
                Encounter.organization_id == org_id,
                Encounter.encounter_date >= datetime.combine(since, time.min, tzinfo=UTC),
                Diagnosis.deleted_at.is_(None),
                Encounter.deleted_at.is_(None),
            )
            .group_by(code_expr, description_expr)
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
