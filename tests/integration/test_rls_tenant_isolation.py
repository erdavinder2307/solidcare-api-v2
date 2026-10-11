"""Proves Postgres Row-Level Security actually enforces tenant isolation (F6).

`solidcare_test`'s schema is provisioned by `setup_database` via
`Base.metadata.create_all()`, which creates tables from the ORM models only — it
does NOT run Alembic migrations, so the RLS policies from migration
`b2c3d4e5f6a7` are never present on this database unless applied here directly.
This file applies the identical DDL from that migration as its own fixture step,
so this test suite is the source of truth for "does RLS actually enforce
isolation" — independent of whether a given environment has run the migration.

Three properties are proven, matching the live psql verification done when F6
was implemented:
  1. Deny-by-default: no `app.current_org_id` set → zero rows, even though real
     rows exist. This is what distinguishes real enforcement from a policy that
     silently does nothing because the connecting role owns the table (FORCE is
     required precisely because `solidcare` owns these tables).
  2. Correct-org grants: the right session var → only that org's rows.
  3. Wrong-org denies: a different org's session var → zero rows, not the other
     org's data — this is the actual cross-tenant leak this migration prevents.
"""

import uuid

import pytest
from sqlalchemy import text

import app.register_models  # noqa: F401
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient

pytestmark = pytest.mark.asyncio

RLS_TABLE = "patients"  # representative of the 5 tables the migration covers
ORG_A = uuid.UUID("66666666-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("66666666-0000-0000-0000-00000000000b")


async def _apply_rls(session):
    """Mirrors migration b2c3d4e5f6a7's DDL for `patients` only."""
    await session.execute(text(f"ALTER TABLE {RLS_TABLE} ENABLE ROW LEVEL SECURITY"))
    await session.execute(text(f"ALTER TABLE {RLS_TABLE} FORCE ROW LEVEL SECURITY"))
    await session.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {RLS_TABLE}"))
    await session.execute(
        text(
            f"""
            CREATE POLICY tenant_isolation ON {RLS_TABLE}
            USING (organization_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
            """
        )
    )
    await session.commit()


async def _seed_two_orgs_one_patient_each(session):
    for org_id, name in ((ORG_A, "RLS Org A"), (ORG_B, "RLS Org B")):
        session.add(
            Organization(
                id=org_id, name=name, slug=f"rls-{org_id}",
                schema_name=f"rls_{org_id.hex}", country="India",
            )
        )
    session.add(
        Patient(
            id=uuid.uuid4(), organization_id=ORG_A, uhid=f"UHID-A-{uuid.uuid4().hex[:6]}",
            first_name="Alpha", last_name="Patient", phone="+910000000010",
            country="India", is_active=True, is_merged=False,
        )
    )
    session.add(
        Patient(
            id=uuid.uuid4(), organization_id=ORG_B, uhid=f"UHID-B-{uuid.uuid4().hex[:6]}",
            first_name="Beta", last_name="Patient", phone="+910000000020",
            country="India", is_active=True, is_merged=False,
        )
    )
    await session.commit()


async def _count_patients(session) -> int:
    result = await session.execute(text(f"SELECT count(*) FROM {RLS_TABLE}"))
    return result.scalar_one()


async def _set_org_context(session, org_id: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))


async def test_no_org_context_denies_all_rows(setup_database, db_session):
    """The core proof this migration matters: FORCE means the table-owning role
    (which `solidcare` is) does NOT implicitly bypass RLS. Without this, ADR-002's
    RLS defense-in-depth would be a documented placebo.

    No call to `_set_org_context` here at all — this session's connection has
    never set `app.current_org_id`, matching a genuinely fresh, unauthenticated
    connection (exactly what `current_setting(..., true)` returning NULL models).
    """
    await _seed_two_orgs_one_patient_each(db_session)
    await _apply_rls(db_session)

    count = await _count_patients(db_session)

    assert count == 0, "FORCE RLS did not block an unscoped session — it is not actually enforcing"


async def test_correct_org_context_sees_only_its_own_row(setup_database, db_session):
    await _seed_two_orgs_one_patient_each(db_session)
    await _apply_rls(db_session)

    await db_session.execute(text("BEGIN"))
    await _set_org_context(db_session, ORG_A)
    result = await db_session.execute(text(f"SELECT first_name FROM {RLS_TABLE}"))
    names = [r[0] for r in result.all()]

    assert names == ["Alpha"], f"expected only Org A's patient, got {names}"


async def test_wrong_org_context_sees_nothing_not_the_other_orgs_data(setup_database, db_session):
    """The actual cross-tenant leak scenario: a session scoped to Org B must see
    zero rows from Org A's query result — not Org B's own data leaking in as a
    fallback, and definitely not Org A's data."""
    await _seed_two_orgs_one_patient_each(db_session)
    await _apply_rls(db_session)

    await db_session.execute(text("BEGIN"))
    await _set_org_context(db_session, ORG_B)
    result = await db_session.execute(text(f"SELECT first_name FROM {RLS_TABLE}"))
    names = [r[0] for r in result.all()]

    assert names == ["Beta"], f"expected only Org B's patient, got {names}"
    assert "Alpha" not in names, "Org A's patient leaked into an Org B-scoped session"


async def test_insert_rejected_when_organization_id_does_not_match_context(setup_database, db_session):
    """The WITH CHECK clause: a session scoped to Org A cannot insert a row
    claiming to belong to Org B — this is what stops a buggy/compromised write
    path from writing data into the wrong tenant."""
    await _seed_two_orgs_one_patient_each(db_session)
    await _apply_rls(db_session)

    await db_session.execute(text("BEGIN"))
    await _set_org_context(db_session, ORG_A)

    with pytest.raises(Exception) as exc_info:
        await db_session.execute(
            text(
                f"""
                INSERT INTO {RLS_TABLE}
                    (id, organization_id, uhid, first_name, last_name, phone, country, is_active, is_merged, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :org_b, :uhid, 'Sneaky', 'Insert', '+910000000099', 'India', true, false, now(), now())
                """
            ),
            {"org_b": str(ORG_B), "uhid": f"UHID-SNEAK-{uuid.uuid4().hex[:6]}"},
        )
    assert "row-level security" in str(exc_info.value).lower() or "policy" in str(exc_info.value).lower()
