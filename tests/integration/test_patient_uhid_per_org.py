"""UHIDs are numbered per organization, so they must be unique per organization only.

`generate_uhid` counts patients inside one organization (PT000001, PT000002, ...),
so every new clinic's first patient gets PT000001. A global unique index on `uhid`
made that insert fail for the second organization (500 on POST /patients).
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

import app.register_models  # noqa: F401
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.patients.repository import PatientRepository

pytestmark = pytest.mark.asyncio

ORG_A = uuid.UUID("77777777-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("77777777-0000-0000-0000-00000000000b")


def _patient(org_id: uuid.UUID, uhid: str, phone: str) -> Patient:
    return Patient(
        id=uuid.uuid4(), organization_id=org_id, uhid=uhid,
        first_name="Test", last_name="Patient", phone=phone,
        country="India", is_active=True, is_merged=False,
    )


async def _seed_orgs(session) -> None:
    for org_id in (ORG_A, ORG_B):
        session.add(
            Organization(
                id=org_id, name=f"UHID {org_id}", slug=f"uhid-{org_id}",
                schema_name=f"uhid_{org_id.hex}", country="India",
            )
        )
    await session.flush()


@pytest.mark.usefixtures("setup_database")
async def test_second_org_first_patient_gets_same_uhid_without_collision(db_session):
    await _seed_orgs(db_session)
    repo = PatientRepository(db_session)

    uhid_a = await repo.generate_uhid(ORG_A)
    db_session.add(_patient(ORG_A, uhid_a, "+910000000101"))
    await db_session.flush()

    uhid_b = await repo.generate_uhid(ORG_B)
    assert uhid_a == uhid_b == "PT000001"
    db_session.add(_patient(ORG_B, uhid_b, "+910000000102"))
    await db_session.flush()  # raised UniqueViolation on the global ix_patients_uhid

    assert await repo.get_by_uhid("PT000001", ORG_A) is not None
    assert await repo.get_by_uhid("PT000001", ORG_B) is not None


@pytest.mark.usefixtures("setup_database")
async def test_uhid_still_unique_inside_one_org(db_session):
    await _seed_orgs(db_session)
    db_session.add(_patient(ORG_A, "PT000001", "+910000000103"))
    await db_session.flush()

    db_session.add(_patient(ORG_A, "PT000001", "+910000000104"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
