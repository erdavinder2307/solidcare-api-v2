"""Coverage for LabOrderService — module had zero tests before this session."""

import uuid
from datetime import UTC, datetime

import pytest

import app.register_models  # noqa: F401
from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.encounters.models import Encounter, EncounterStatus, EncounterType
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.lab_orders.models import LabOrderStatus
from app.modules.clinical.lab_orders.repository import LabOrderRepository
from app.modules.clinical.lab_orders.schemas import (
    LabOrderCreate,
    LabOrderItemCreate,
    LabResultCreate,
)
from app.modules.clinical.lab_orders.service import LabOrderService
from app.modules.clinics.models import Clinic
from app.modules.doctors.models import Doctor, DoctorStatus
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.users.models import User, UserStatus

pytestmark = pytest.mark.asyncio

ORG_ID = uuid.UUID("55555555-0000-0000-0000-000000000001")
CLINIC_ID = uuid.UUID("55555555-0000-0000-0000-000000000010")
PATIENT_ID = uuid.UUID("55555555-0000-0000-0000-000000000050")
DOCTOR_ID = uuid.UUID("55555555-0000-0000-0000-0000000000d1")
DOCTOR_USER_ID = uuid.UUID("55555555-0000-0000-0000-000000000091")


async def _seed(session) -> uuid.UUID:
    """Seeds org/clinic/patient/doctor plus one IN_PROGRESS encounter. Returns encounter_id."""
    session.add(
        Organization(
            id=ORG_ID,
            name="Lab Test Org",
            slug=f"lab-{uuid.uuid4().hex[:8]}",
            schema_name=f"lab_{uuid.uuid4().hex[:8]}",
            country="India",
        )
    )
    session.add(Clinic(id=CLINIC_ID, organization_id=ORG_ID, name="Test Clinic", code="LAB01"))
    session.add(
        Patient(
            id=PATIENT_ID,
            organization_id=ORG_ID,
            uhid="UHID-LAB-001",
            first_name="Lab",
            last_name="Patient",
            phone="+910000000002",
            country="India",
            is_active=True,
            is_merged=False,
        )
    )
    session.add(
        User(
            id=DOCTOR_USER_ID,
            organization_id=ORG_ID,
            email=f"lab-doc-{uuid.uuid4().hex[:8]}@solidcare.test",
            hashed_password="x",
            first_name="Lab",
            last_name="Doctor",
            status=UserStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(Doctor(id=DOCTOR_ID, organization_id=ORG_ID, user_id=DOCTOR_USER_ID, status=DoctorStatus.ACTIVE))
    await session.flush()

    encounter_id = uuid.uuid4()
    session.add(
        Encounter(
            id=encounter_id,
            organization_id=ORG_ID,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            encounter_type=EncounterType.OPD,
            status=EncounterStatus.IN_PROGRESS,
            encounter_date=datetime.now(UTC),
        )
    )
    await session.flush()
    return encounter_id


def _svc(session):
    return LabOrderService(LabOrderRepository(session), EncounterRepository(session))


def _order_data(encounter_id, **overrides) -> LabOrderCreate:
    base = dict(
        encounter_id=encounter_id,
        patient_id=PATIENT_ID,
        ordered_by_id=DOCTOR_ID,
        lab_name="City Diagnostics",
        items=[LabOrderItemCreate(test_name="CBC")],
    )
    base.update(overrides)
    return LabOrderCreate(**base)


async def test_create_lab_order_with_items(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)

    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)

    assert order.status == LabOrderStatus.ORDERED
    assert order.patient_id == PATIENT_ID
    assert order.ordered_at is not None


async def test_create_lab_order_unknown_encounter_raises_not_found(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    with pytest.raises(NotFoundError):
        await svc.create(ORG_ID, _order_data(uuid.uuid4()), created_by=DOCTOR_USER_ID)


async def test_create_lab_order_patient_mismatch_raises_business_rule_error(setup_database, db_session):
    """The order's patient_id must match the encounter's patient_id."""
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)

    with pytest.raises(BusinessRuleError):
        await svc.create(ORG_ID, _order_data(encounter_id, patient_id=uuid.uuid4()), created_by=DOCTOR_USER_ID)


async def test_get_scoped_to_organization(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)

    with pytest.raises(NotFoundError):
        await svc.get(order.id, uuid.uuid4())


async def test_list_for_encounter(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)

    orders = await svc.list_for_encounter(encounter_id, ORG_ID)

    assert order.id in {o.id for o in orders}


async def test_add_result_marks_order_resulted(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)

    updated = await svc.add_result(
        order.id, ORG_ID, [LabResultCreate(test_name="Hemoglobin", value="13.5", unit="g/dL", is_abnormal=False)]
    )

    assert updated.status == LabOrderStatus.RESULTED
    assert updated.resulted_at is not None


async def test_add_result_to_cancelled_order_is_rejected(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)
    await svc.cancel(order.id, ORG_ID)

    with pytest.raises(BusinessRuleError):
        await svc.add_result(order.id, ORG_ID, [LabResultCreate(test_name="CBC", value="x")])


async def test_cancel_order(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)

    cancelled = await svc.cancel(order.id, ORG_ID)

    assert cancelled.status == LabOrderStatus.CANCELLED


async def test_cancel_resulted_order_is_rejected(setup_database, db_session):
    """A resulted order is final and must not be cancellable."""
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)
    await svc.add_result(order.id, ORG_ID, [LabResultCreate(test_name="CBC", value="x")])

    with pytest.raises(BusinessRuleError):
        await svc.cancel(order.id, ORG_ID)


async def test_cancel_already_cancelled_order_is_rejected(setup_database, db_session):
    encounter_id = await _seed(db_session)
    svc = _svc(db_session)
    order = await svc.create(ORG_ID, _order_data(encounter_id), created_by=DOCTOR_USER_ID)
    await svc.cancel(order.id, ORG_ID)

    with pytest.raises(BusinessRuleError):
        await svc.cancel(order.id, ORG_ID)
