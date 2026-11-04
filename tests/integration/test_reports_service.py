"""Coverage for ReportsService methods not covered by test_reports_regressions.py.

Complements the regression suite: this file exercises outstanding_aging,
patient_demographics, dashboard_kpis, appointment_type_distribution and daily_opd —
none of which had any test before this session (module had zero coverage).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import app.register_models  # noqa: F401
from app.modules.appointments.models import Appointment, AppointmentStatus, AppointmentType
from app.modules.billing.invoices.models import Invoice, InvoiceStatus
from app.modules.clinics.models import Clinic
from app.modules.doctors.models import Doctor, DoctorStatus
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.reports.service import ReportsService
from app.modules.users.models import User, UserStatus

pytestmark = pytest.mark.asyncio

ORG_ID = uuid.UUID("33333333-0000-0000-0000-000000000001")
CLINIC_ID = uuid.UUID("33333333-0000-0000-0000-000000000010")
DOCTOR_ID = uuid.UUID("33333333-0000-0000-0000-0000000000d1")
DOCTOR_USER_ID = uuid.UUID("33333333-0000-0000-0000-000000000091")


async def _seed_org_clinic(session):
    session.add(
        Organization(
            id=ORG_ID,
            name="Reports Test Org",
            slug=f"reports-{uuid.uuid4().hex[:8]}",
            schema_name=f"reports_{uuid.uuid4().hex[:8]}",
            country="India",
        )
    )
    session.add(Clinic(id=CLINIC_ID, organization_id=ORG_ID, name="Test Clinic", code="RPT01"))
    session.add(
        User(
            id=DOCTOR_USER_ID,
            organization_id=ORG_ID,
            email=f"reports-doc-{uuid.uuid4().hex[:8]}@solidcare.test",
            hashed_password="x",
            first_name="Report",
            last_name="Doctor",
            status=UserStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(Doctor(id=DOCTOR_ID, organization_id=ORG_ID, user_id=DOCTOR_USER_ID, status=DoctorStatus.ACTIVE))
    await session.flush()


async def _add_patient(session, *, gender=None, dob=None, city=None, created_at=None) -> uuid.UUID:
    pid = uuid.uuid4()
    p = Patient(
        id=pid,
        organization_id=ORG_ID,
        uhid=f"UHID-{uuid.uuid4().hex[:8]}",
        first_name="Test",
        last_name="Patient",
        phone=f"+91{uuid.uuid4().int % 10**10:010d}",
        country="India",
        is_active=True,
        is_merged=False,
        gender=gender,
        date_of_birth=dob,
        city=city,
    )
    session.add(p)
    await session.flush()
    if created_at:
        # created_at has a server default; override post-insert for deterministic "new patient" tests.
        p.created_at = created_at
        await session.flush()
    return pid


async def _add_invoice(session, patient_id, *, status, outstanding, invoice_date, total=1000.0) -> uuid.UUID:
    inv_id = uuid.uuid4()
    session.add(
        Invoice(
            id=inv_id,
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            patient_id=patient_id,
            invoice_number=f"INV-RPT-{uuid.uuid4().hex[:8]}",
            invoice_date=invoice_date,
            status=status,
            subtotal=total,
            taxable_amount=total,
            total_amount=total,
            paid_amount=total - outstanding,
            outstanding_amount=outstanding,
        )
    )
    await session.flush()
    return inv_id


async def _add_appointment(session, patient_id, *, appt_date, status, appt_type=AppointmentType.WALK_IN):
    session.add(
        Appointment(
            id=uuid.uuid4(),
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            patient_id=patient_id,
            doctor_id=DOCTOR_ID,
            appointment_date=appt_date,
            start_time="09:00:00",
            appointment_type=appt_type,
            status=status,
        )
    )
    await session.flush()


# ---------------------------------------------------------------------------
# outstanding_aging
# ---------------------------------------------------------------------------


async def test_outstanding_aging_buckets_by_invoice_age(setup_database, db_session):
    await _seed_org_clinic(db_session)
    patient = await _add_patient(db_session)
    today = date.today()

    await _add_invoice(db_session, patient, status=InvoiceStatus.ISSUED, outstanding=500.0, invoice_date=today - timedelta(days=10))
    await _add_invoice(db_session, patient, status=InvoiceStatus.ISSUED, outstanding=300.0, invoice_date=today - timedelta(days=45))
    await _add_invoice(db_session, patient, status=InvoiceStatus.ISSUED, outstanding=200.0, invoice_date=today - timedelta(days=100))

    result = await ReportsService(db_session).outstanding_aging(ORG_ID, as_of=today)

    assert result["total_outstanding"] == 1000.0
    assert result["total_invoices"] == 3
    by_key = {b["key"]: b for b in result["buckets"]}
    assert by_key["current"]["amount"] == 500.0
    assert by_key["days_31_60"]["amount"] == 300.0
    assert by_key["over_90"]["amount"] == 200.0


async def test_outstanding_aging_excludes_fully_paid_invoices(setup_database, db_session):
    await _seed_org_clinic(db_session)
    patient = await _add_patient(db_session)

    await _add_invoice(db_session, patient, status=InvoiceStatus.PAID, outstanding=0.0, invoice_date=date.today())

    result = await ReportsService(db_session).outstanding_aging(ORG_ID)

    assert result["total_invoices"] == 0
    assert result["total_outstanding"] == 0.0


# ---------------------------------------------------------------------------
# patient_demographics
# ---------------------------------------------------------------------------


async def test_patient_demographics_counts_and_distributions(setup_database, db_session):
    await _seed_org_clinic(db_session)
    await _add_patient(db_session, gender="male", city="Chandigarh")
    await _add_patient(db_session, gender="male", city="Chandigarh")
    await _add_patient(db_session, gender="female", city="Zirakpur")

    result = await ReportsService(db_session).patient_demographics(ORG_ID)

    assert result["total_patients"] == 3
    assert result["gender_distribution"]["male"] == 2
    assert result["gender_distribution"]["female"] == 1
    assert result["city_distribution"]["Chandigarh"] == 2


async def test_patient_demographics_new_patients_last_30_days(setup_database, db_session):
    await _seed_org_clinic(db_session)
    now = datetime.now(UTC)
    await _add_patient(db_session, created_at=now)
    await _add_patient(db_session, created_at=now - timedelta(days=45))

    result = await ReportsService(db_session).patient_demographics(ORG_ID)

    assert result["total_patients"] == 2
    assert result["new_patients"] == 1


# ---------------------------------------------------------------------------
# dashboard_kpis
# ---------------------------------------------------------------------------


async def test_dashboard_kpis_counts_todays_appointments(setup_database, db_session):
    await _seed_org_clinic(db_session)
    patient = await _add_patient(db_session)
    today = date.today()

    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.SCHEDULED)
    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.COMPLETED)
    await _add_appointment(db_session, patient, appt_date=today - timedelta(days=1), status=AppointmentStatus.SCHEDULED)

    kpis = await ReportsService(db_session).dashboard_kpis(ORG_ID, report_date=today)

    assert kpis["today_appointments"] == 2
    assert kpis["today_revenue"] == 0.0


# ---------------------------------------------------------------------------
# appointment_type_distribution
# ---------------------------------------------------------------------------


async def test_appointment_type_distribution_groups_by_type(setup_database, db_session):
    await _seed_org_clinic(db_session)
    patient = await _add_patient(db_session)
    today = date.today()

    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.SCHEDULED, appt_type=AppointmentType.WALK_IN)
    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.SCHEDULED, appt_type=AppointmentType.WALK_IN)
    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.SCHEDULED, appt_type=AppointmentType.FOLLOW_UP)

    result = await ReportsService(db_session).appointment_type_distribution(ORG_ID, days=30)

    by_type = {r["type"]: r["count"] for r in result}
    assert by_type[AppointmentType.WALK_IN] == 2
    assert by_type[AppointmentType.FOLLOW_UP] == 1


# ---------------------------------------------------------------------------
# daily_opd — doctor_wise breakdown (fixed this session; was always [])
# ---------------------------------------------------------------------------


async def test_daily_opd_doctor_wise_breakdown(setup_database, db_session):
    await _seed_org_clinic(db_session)
    patient = await _add_patient(db_session)
    today = date.today()

    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.COMPLETED)
    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.CANCELLED)
    await _add_appointment(db_session, patient, appt_date=today, status=AppointmentStatus.NO_SHOW)

    result = await ReportsService(db_session).daily_opd(ORG_ID, CLINIC_ID, today)

    assert result["total_appointments"] == 3
    assert result["completed"] == 1
    assert result["cancelled"] == 1
    assert result["no_show"] == 1
    assert len(result["doctor_wise"]) == 1
    bucket = result["doctor_wise"][0]
    assert bucket["doctor_id"] == str(DOCTOR_ID)
    assert bucket["total"] == 3
    assert bucket["completed"] == 1
