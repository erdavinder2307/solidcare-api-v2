"""Coverage for EncounterService — module had zero tests before this session."""

import uuid

import pytest
from sqlalchemy import select

import app.register_models  # noqa: F401
from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import EncounterStatus, EncounterType
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.encounters.schemas import (
    DiagnosisCreate,
    EncounterCreate,
    EncounterUpdate,
    VitalCreate,
)
from app.modules.clinical.encounters.service import EncounterService
from app.modules.clinics.models import Clinic
from app.modules.doctors.models import Doctor, DoctorStatus
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.users.models import User, UserStatus
from app.shared.schemas.pagination import PaginationParams

pytestmark = pytest.mark.asyncio

ORG_ID = uuid.UUID("44444444-0000-0000-0000-000000000001")
CLINIC_ID = uuid.UUID("44444444-0000-0000-0000-000000000010")
PATIENT_ID = uuid.UUID("44444444-0000-0000-0000-000000000050")
DOCTOR_ID = uuid.UUID("44444444-0000-0000-0000-0000000000d1")
DOCTOR_USER_ID = uuid.UUID("44444444-0000-0000-0000-000000000091")
CREATOR_ID = uuid.UUID("44444444-0000-0000-0000-000000000092")


async def _seed(session):
    session.add(
        Organization(
            id=ORG_ID,
            name="Clinical Test Org",
            slug=f"clinical-{uuid.uuid4().hex[:8]}",
            schema_name=f"clinical_{uuid.uuid4().hex[:8]}",
            country="India",
        )
    )
    session.add(Clinic(id=CLINIC_ID, organization_id=ORG_ID, name="Test Clinic", code="CLN01"))
    session.add(
        Patient(
            id=PATIENT_ID,
            organization_id=ORG_ID,
            uhid="UHID-CLN-001",
            first_name="Clinical",
            last_name="Patient",
            phone="+910000000001",
            country="India",
            is_active=True,
            is_merged=False,
        )
    )
    for uid in (DOCTOR_USER_ID, CREATOR_ID):
        session.add(
            User(
                id=uid,
                organization_id=ORG_ID,
                email=f"clinical-{uuid.uuid4().hex[:8]}@solidcare.test",
                hashed_password="x",
                first_name="Clin",
                last_name="User",
                status=UserStatus.ACTIVE,
            )
        )
    await session.flush()
    session.add(Doctor(id=DOCTOR_ID, organization_id=ORG_ID, user_id=DOCTOR_USER_ID, status=DoctorStatus.ACTIVE))
    await session.flush()


def _svc(session):
    return EncounterService(EncounterRepository(session))


def _create_data(**overrides) -> EncounterCreate:
    base = dict(
        clinic_id=CLINIC_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        encounter_type=EncounterType.OPD,
        chief_complaint="Fever",
    )
    base.update(overrides)
    return EncounterCreate(**base)


async def test_create_encounter_basic(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    assert encounter.id is not None
    assert encounter.status == EncounterStatus.IN_PROGRESS
    assert encounter.chief_complaint == "Fever"
    assert encounter.organization_id == ORG_ID


async def test_create_encounter_with_vitals_and_diagnosis(setup_database, db_session):
    """Vitals and diagnoses passed at creation must be persisted as side rows."""
    await _seed(db_session)
    svc = _svc(db_session)

    data = _create_data(
        vitals=VitalCreate(systolic_bp=120, diastolic_bp=80, pulse_rate=72),
        diagnoses=[DiagnosisCreate(icd10_code="J06.9", diagnosis_type="primary")],
    )
    encounter = await svc.create(ORG_ID, data, created_by=CREATOR_ID)

    fetched = await svc.get(encounter.id, ORG_ID)
    assert len(fetched.vitals) == 1
    assert fetched.vitals[0].systolic_bp == 120
    assert len(fetched.diagnoses) == 1
    assert fetched.diagnoses[0].icd10_code == "J06.9"


async def test_get_unknown_encounter_raises_not_found(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4(), ORG_ID)


async def test_get_scoped_to_organization(setup_database, db_session):
    """An encounter must not be fetchable using a different org_id."""
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    with pytest.raises(NotFoundError):
        await svc.get(encounter.id, uuid.uuid4())


async def test_update_encounter_fields(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    updated = await svc.update(
        encounter.id, ORG_ID, EncounterUpdate(clinical_impression="Viral fever, resolving")
    )

    assert updated.clinical_impression == "Viral fever, resolving"


async def test_update_completed_encounter_raises_business_rule_error(setup_database, db_session):
    """A completed encounter must be immutable via update()."""
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    # Bypass complete() (which triggers PDF generation) — set status directly to
    # isolate the guard under test.
    encounter.status = EncounterStatus.COMPLETED
    await db_session.flush()

    with pytest.raises(BusinessRuleError):
        await svc.update(encounter.id, ORG_ID, EncounterUpdate(clinical_impression="edit"))


async def test_list_for_patient_scoped_and_ordered(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    first = await svc.create(ORG_ID, _create_data(chief_complaint="Visit 1"), created_by=CREATOR_ID)
    second = await svc.create(ORG_ID, _create_data(chief_complaint="Visit 2"), created_by=CREATOR_ID)

    result = await svc.list_for_patient(PATIENT_ID, ORG_ID, PaginationParams(page=1, page_size=20))

    ids = {e.id for e in result.items}
    assert {first.id, second.id} <= ids


# ---------------------------------------------------------------------------
# Vitals and diagnoses — managed through EncounterService (no sub-module service)
# ---------------------------------------------------------------------------


async def test_add_vitals_to_encounter(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    vital = await svc.add_vitals(
        encounter.id, ORG_ID, VitalCreate(systolic_bp=130, diastolic_bp=85, pulse_rate=78)
    )

    assert vital.encounter_id == encounter.id
    assert vital.patient_id == PATIENT_ID
    assert vital.systolic_bp == 130
    assert vital.recorded_at is not None


async def test_add_diagnosis_to_encounter(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)

    dx = await svc.add_diagnosis(
        encounter.id, ORG_ID, DiagnosisCreate(icd10_code="B34.9", diagnosis_type="provisional")
    )

    assert dx.encounter_id == encounter.id
    assert dx.patient_id == PATIENT_ID
    assert dx.icd10_code == "B34.9"


async def test_remove_diagnosis_from_encounter(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(
        ORG_ID,
        _create_data(diagnoses=[DiagnosisCreate(icd10_code="J06.9", diagnosis_type="primary")]),
        created_by=CREATOR_ID,
    )
    fetched = await svc.get(encounter.id, ORG_ID)
    dx_id = fetched.diagnoses[0].id

    await svc.remove_diagnosis(encounter.id, dx_id, ORG_ID)
    await db_session.flush()

    remaining = (
        await db_session.execute(select(Diagnosis.id).where(Diagnosis.encounter_id == encounter.id))
    ).scalars().all()
    assert dx_id not in remaining


async def test_add_diagnosis_to_completed_encounter_is_rejected(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)
    encounter.status = EncounterStatus.COMPLETED
    await db_session.flush()

    with pytest.raises(BusinessRuleError):
        await svc.add_diagnosis(
            encounter.id, ORG_ID, DiagnosisCreate(icd10_code="B34.9", diagnosis_type="provisional")
        )


async def test_remove_diagnosis_from_completed_encounter_is_rejected(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(
        ORG_ID,
        _create_data(diagnoses=[DiagnosisCreate(icd10_code="J06.9", diagnosis_type="primary")]),
        created_by=CREATOR_ID,
    )
    fetched = await svc.get(encounter.id, ORG_ID)
    dx_id = fetched.diagnoses[0].id

    encounter.status = EncounterStatus.COMPLETED
    await db_session.flush()

    with pytest.raises(BusinessRuleError):
        await svc.remove_diagnosis(encounter.id, dx_id, ORG_ID)


async def test_add_vitals_to_completed_encounter_is_currently_allowed(setup_database, db_session):
    """Documents an asymmetry in the service, not an endorsement of it.

    `add_diagnosis` and `remove_diagnosis` both reject completed encounters, but
    `add_vitals` has no such guard. This test pins the current behaviour so the
    inconsistency is visible and any future change is deliberate rather than silent.
    """
    await _seed(db_session)
    svc = _svc(db_session)
    encounter = await svc.create(ORG_ID, _create_data(), created_by=CREATOR_ID)
    encounter.status = EncounterStatus.COMPLETED
    await db_session.flush()

    vital = await svc.add_vitals(encounter.id, ORG_ID, VitalCreate(pulse_rate=80))

    assert vital.encounter_id == encounter.id
