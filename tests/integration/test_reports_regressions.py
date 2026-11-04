"""Regression tests for three reporting bugs found on 2026-07-28.

All three were SQL-generation bugs — wrong bind parameters, timezone-dependent
`date_trunc`, and an over-narrow status filter. None of them would be caught by a
mocked unit test, because in every case the Python looked correct and the *generated
SQL* was wrong. These tests therefore execute real queries against Postgres.

Bugs covered:

1. ``top_diagnoses`` raised HTTP 500.
   ``coalesce(...)`` was built twice — once for SELECT, once for GROUP BY — emitting
   different bind parameters, so Postgres rejected it with
   "column must appear in the GROUP BY clause". The chart had never rendered.

2. ``revenue_trend`` always returned zero for every week.
   ``date_trunc('week', paid_at)`` ran in the DB session timezone, returning
   Monday-00:00-local. Read back in UTC that is the *previous* day (Sunday), which
   never matched the Monday keys generated in Python, so every bucket resolved to 0.

3. Revenue sums ignored refunds.
   Filtering on ``status == COMPLETED`` skipped the negative ``REFUNDED`` rows that a
   refund writes, overstating revenue.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest

import app.register_models  # noqa: F401
from app.modules.billing.invoices.models import Invoice, InvoiceStatus
from app.modules.billing.payments.models import Payment, PaymentMethod, PaymentStatus
from app.modules.clinical.diagnoses.models import Diagnosis, DiagnosisStatus, DiagnosisType
from app.modules.clinical.encounters.models import Encounter, EncounterStatus
from app.modules.clinics.models import Clinic
from app.modules.doctors.models import Doctor, DoctorStatus
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.reports.service import ReportsService
from app.modules.users.models import User, UserStatus

pytestmark = pytest.mark.asyncio

ORG_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")
CLINIC_ID = uuid.UUID("11111111-0000-0000-0000-000000000010")
PATIENT_ID = uuid.UUID("11111111-0000-0000-0000-000000000050")
DOCTOR_ID = uuid.UUID("11111111-0000-0000-0000-0000000000d1")
USER_ID = uuid.UUID("11111111-0000-0000-0000-000000000091")


async def _seed_base(session):
    """Minimum graph: org → clinic → patient. Returns nothing; ids are module constants."""
    session.add(
        Organization(
            id=ORG_ID,
            name="Regression Test Org",
            slug=f"regression-{uuid.uuid4().hex[:8]}",
            schema_name=f"regression_{uuid.uuid4().hex[:8]}",
            country="India",
        )
    )
    session.add(Clinic(id=CLINIC_ID, organization_id=ORG_ID, name="Test Clinic", code="RGT01"))
    # Encounters FK to doctors, which in turn FKs to users.
    session.add(
        User(
            id=USER_ID,
            organization_id=ORG_ID,
            email=f"regression-{uuid.uuid4().hex[:8]}@solidcare.test",
            hashed_password="x",
            first_name="Reg",
            last_name="Doctor",
            status=UserStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(
        Doctor(
            id=DOCTOR_ID,
            organization_id=ORG_ID,
            user_id=USER_ID,
            status=DoctorStatus.ACTIVE,
        )
    )
    session.add(
        Patient(
            id=PATIENT_ID,
            organization_id=ORG_ID,
            uhid="UHID-RGT-001",
            first_name="Regression",
            last_name="Patient",
            phone="+910000000000",
            country="India",
            is_active=True,
            is_merged=False,
        )
    )
    await session.flush()


async def _add_encounter(session, when: datetime) -> uuid.UUID:
    enc_id = uuid.uuid4()
    session.add(
        Encounter(
            id=enc_id,
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            encounter_type="OPD",
            status=EncounterStatus.COMPLETED,
            encounter_date=when,
        )
    )
    await session.flush()
    return enc_id


async def _add_payment(session, invoice_id, amount, status, paid_at):
    session.add(
        Payment(
            id=uuid.uuid4(),
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            invoice_id=invoice_id,
            patient_id=PATIENT_ID,
            payment_method=PaymentMethod.CASH,
            status=status,
            amount=amount,
            paid_at=paid_at,
        )
    )
    await session.flush()


async def _add_invoice(session, encounter_id=None, total=1000.0) -> uuid.UUID:
    inv_id = uuid.uuid4()
    session.add(
        Invoice(
            id=inv_id,
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            encounter_id=encounter_id,
            invoice_number=f"INV-RGT-{uuid.uuid4().hex[:8]}",
            invoice_date=date.today(),
            status=InvoiceStatus.PAID,
            subtotal=total,
            taxable_amount=total,
            total_amount=total,
            paid_amount=total,
            outstanding_amount=0.0,
        )
    )
    await session.flush()
    return inv_id


# ---------------------------------------------------------------------------
# Bug 1 — top_diagnoses GROUP BY / bind-parameter mismatch
# ---------------------------------------------------------------------------


async def test_top_diagnoses_executes_without_group_by_error(setup_database, db_session):
    """Regression: the query raised a Postgres GroupingError and 500'd.

    Building `coalesce(...)` separately for SELECT and GROUP BY emitted distinct bind
    params, so Postgres saw two different expressions. Merely *executing* this without
    raising is the core assertion.
    """
    await _seed_base(db_session)
    enc = await _add_encounter(db_session, datetime.now(UTC))
    db_session.add(
        Diagnosis(
            id=uuid.uuid4(),
            encounter_id=enc,
            patient_id=PATIENT_ID,
            icd10_code="B34.9",
            icd10_description="Viral infection, unspecified",
            diagnosis_type=DiagnosisType.PROVISIONAL,
            status=DiagnosisStatus.ACTIVE,
            is_chronic=False,
        )
    )
    await db_session.flush()

    rows = await ReportsService(db_session).top_diagnoses(ORG_ID, days=90, limit=10)

    assert isinstance(rows, list)
    codes = {r["code"] for r in rows}
    assert "B34.9" in codes, f"seeded diagnosis missing from results: {rows}"


async def test_top_diagnoses_groups_duplicates(setup_database, db_session):
    """Two diagnoses with the same code must collapse into one row with count=2."""
    await _seed_base(db_session)
    for _ in range(2):
        enc = await _add_encounter(db_session, datetime.now(UTC))
        db_session.add(
            Diagnosis(
                id=uuid.uuid4(),
                encounter_id=enc,
                patient_id=PATIENT_ID,
                icd10_code="J06.9",
                icd10_description="Acute upper respiratory infection",
                diagnosis_type=DiagnosisType.PRIMARY,
                status=DiagnosisStatus.ACTIVE,
                is_chronic=False,
            )
        )
    await db_session.flush()

    rows = await ReportsService(db_session).top_diagnoses(ORG_ID, days=90, limit=10)

    match = [r for r in rows if r["code"] == "J06.9"]
    assert len(match) == 1, f"expected grouping into a single row, got {match}"
    assert match[0]["count"] == 2


# ---------------------------------------------------------------------------
# Bug 2 — revenue_trend week bucketing lost every payment
# ---------------------------------------------------------------------------


async def test_revenue_trend_places_payment_in_correct_week(setup_database, db_session):
    """Regression: every bucket resolved to 0 regardless of payment data.

    This fails on any DB session whose timezone is not UTC when `date_trunc` is applied
    directly to a timestamptz — which is exactly how the bug reached production.
    """
    await _seed_base(db_session)
    inv = await _add_invoice(db_session, total=2000.0)

    # Pay mid-week so the Monday bucket is unambiguous.
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    paid_at = datetime.combine(this_monday + timedelta(days=2), time(12, 0), tzinfo=UTC)
    await _add_payment(db_session, inv, 2000.0, PaymentStatus.COMPLETED, paid_at)

    trend = await ReportsService(db_session).revenue_trend(ORG_ID, weeks=4)

    total = sum(w["revenue"] for w in trend)
    assert total == 2000.0, f"payment lost during week bucketing: {trend}"

    current = [w for w in trend if w["week"] == str(this_monday)]
    assert current, f"current week {this_monday} missing from trend: {[w['week'] for w in trend]}"
    assert current[0]["revenue"] == 2000.0


async def test_revenue_trend_week_keys_are_mondays(setup_database, db_session):
    """The generated buckets must be Mondays — the bug produced Sunday keys from SQL."""
    await _seed_base(db_session)

    trend = await ReportsService(db_session).revenue_trend(ORG_ID, weeks=6)

    assert len(trend) == 6
    for week in trend:
        parsed = date.fromisoformat(week["week"])
        assert parsed.weekday() == 0, f"bucket {week['week']} is not a Monday"


# ---------------------------------------------------------------------------
# Bug 3 — revenue sums ignored refunds
# ---------------------------------------------------------------------------


async def test_revenue_trend_nets_out_refunds(setup_database, db_session):
    """A refund writes a negative REFUNDED row; revenue must be net, not gross."""
    await _seed_base(db_session)
    inv = await _add_invoice(db_session, total=2000.0)

    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    paid_at = datetime.combine(this_monday + timedelta(days=2), time(12, 0), tzinfo=UTC)

    await _add_payment(db_session, inv, 2000.0, PaymentStatus.COMPLETED, paid_at)
    await _add_payment(db_session, inv, -500.0, PaymentStatus.REFUNDED, paid_at)

    trend = await ReportsService(db_session).revenue_trend(ORG_ID, weeks=4)
    total = sum(w["revenue"] for w in trend)

    assert total == 1500.0, f"refund not netted out of revenue (got {total}, expected 1500)"


async def test_dashboard_kpi_revenue_nets_out_refunds(setup_database, db_session):
    """Same fix must hold on the dashboard KPI, which uses a separate query."""
    await _seed_base(db_session)
    inv = await _add_invoice(db_session, total=1000.0)

    now = datetime.now(UTC)
    await _add_payment(db_session, inv, 1000.0, PaymentStatus.COMPLETED, now)
    await _add_payment(db_session, inv, -250.0, PaymentStatus.REFUNDED, now)

    kpis = await ReportsService(db_session).dashboard_kpis(ORG_ID)

    assert kpis["today_revenue"] == 750.0, (
        f"dashboard revenue ignored the refund (got {kpis['today_revenue']}, expected 750)"
    )


async def test_doctor_summary_revenue_nets_out_refunds(setup_database, db_session):
    """Doctor attribution walks encounter → invoice → payment; must also net refunds."""
    await _seed_base(db_session)
    now = datetime.now(UTC)
    enc = await _add_encounter(db_session, now)
    inv = await _add_invoice(db_session, encounter_id=enc, total=1200.0)

    await _add_payment(db_session, inv, 1200.0, PaymentStatus.COMPLETED, now)
    await _add_payment(db_session, inv, -400.0, PaymentStatus.REFUNDED, now)

    today = date.today()
    summary = await ReportsService(db_session).doctor_summary(
        ORG_ID, DOCTOR_ID, today - timedelta(days=7), today
    )

    assert summary["revenue_generated"] == 800.0, (
        f"doctor revenue ignored the refund (got {summary['revenue_generated']}, expected 800)"
    )
