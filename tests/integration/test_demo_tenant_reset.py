"""Proves the demo-tenant reset never touches another tenant, on a real Postgres (SE-4193, D4).

The unit tests (tests/unit/test_reset_demo_tenant.py) only compile the DELETEs to SQL.
This file runs the real reset against a real schema with two tenants:

- the demo org, seeded by the real seed, plus rows a "visitor" added to it;
- a real (non-demo) org with a full set of data in every table the seed writes
  (users, roles, doctors, patients, appointments, encounters, prescriptions,
  invoices, payments, ...), built from the seed's own generator re-keyed to that org;
- users who are members of both orgs (one with the real org as home, one with the demo org).

It then asserts that every real-org row is unchanged, that the shared users and
their demo memberships and role survive, that the visitor rows are gone, and
that the demo org is back to exactly the seeded counts.

The test runs twice: without RLS, where the reset's own WHERE clauses are the only
protection, and (like test_rls_tenant_isolation.py) with Row-Level Security applied to
the five RLS tables (mirroring migration b2c3d4e5f6a7) and as a role RLS applies to,
so the RLS effect on the reset's subqueries is exercised too.
"""

import uuid
from datetime import date
from enum import Enum

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

import app.register_models  # noqa: F401
from app.core.demo_tenant.reset import reset_demo_tenant
from app.core.demo_tenant.seed import (
    DEMO_CLINIC_ID,
    DEMO_ORG_ID,
    SOURCE_ROLE_IDS,
    TABLE_ORDER,
    _id,
    apply_plan,
    build_plan,
)
from app.database import Base
from app.modules.organizations.models import MembershipStatus

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 11, 12)
DEFAULT_ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")  # owns the RBAC seed roles
REAL_ORG = uuid.UUID("77777777-0000-0000-0000-00000000000a")
REAL_CLINIC = uuid.UUID("77777777-0000-0000-0000-0000000000c1")
RLS_TABLES = ["patients", "encounters", "invoices", "payments", "appointments"]
PROBE_ROLE = "demo_reset_probe"
SEED_HASH = "seeded-hash"


async def _insert(session, name: str, rows: list[dict]) -> None:
    if rows:
        await session.execute(insert(Base.metadata.tables[name]).values(rows).on_conflict_do_nothing())


async def _ensure_rbac_seed_roles(session) -> None:
    """The seed copies permissions from the RBAC seed roles (migration c4e8a1b2d903).

    `setup_database` builds the schema with create_all (no migration data), so make
    sure those roles exist with at least one permission each. No-op where they do.
    """
    await _insert(session, "organizations", [{
        "id": DEFAULT_ORG, "name": "Default Org", "slug": "default-org-reset-test",
        "schema_name": "default_org_reset_test", "country": "India",
    }])
    perm_id = uuid.uuid4()
    await _insert(session, "permissions", [{
        "id": perm_id, "name": "Read Patient", "slug": f"patient:read-{perm_id.hex[:6]}",
        "resource": "patient", "action": "read",
    }])
    await _insert(session, "roles", [
        {"id": rid, "organization_id": DEFAULT_ORG, "name": slug.title(), "slug": slug}
        for slug, rid in SOURCE_ROLE_IDS.items()
    ])
    await _insert(session, "role_permissions", [
        {"id": uuid.uuid4(), "role_id": rid, "permission_id": perm_id}
        for rid in SOURCE_ROLE_IDS.values()
    ])


def _real_org_rows() -> dict[str, list[dict]]:
    """The seed's own rows for every table, re-keyed to REAL_ORG (not a demo org)."""
    plan = build_plan(seed=7, today=TODAY, n_patients=5)
    ids: dict[uuid.UUID, uuid.UUID] = {DEMO_ORG_ID: REAL_ORG, DEMO_CLINIC_ID: REAL_CLINIC}

    def remap(value):
        if isinstance(value, Enum):
            return value
        if isinstance(value, uuid.UUID):
            return ids.setdefault(value, uuid.uuid4())
        if isinstance(value, str):
            return value.replace("DEMO", "REAL").replace("demo", "real")
        return value

    tables = {name: [{k: remap(v) for k, v in row.items()} for row in rows]
              for name, rows in plan.tables.items()}
    tables["organizations"][0]["is_demo"] = False
    for user in tables["users"]:
        user["hashed_password"] = "real-org-hash"
    return tables


async def _apply_rls_and_probe_role(session) -> bool:
    """Mirror migration b2c3d4e5f6a7 and create a role RLS applies to. Returns True
    when the current role bypasses RLS (CI's superuser), i.e. the probe role is needed."""
    for table in RLS_TABLES:
        await session.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        await session.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        await session.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        await session.execute(text(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = current_setting('app.current_org_id', true)::uuid) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
        ))
    bypass = (await session.execute(text(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"))).scalar_one()
    if bypass:
        await session.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') "
            f"THEN CREATE ROLE {PROBE_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"))
        await session.execute(text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PROBE_ROLE}"))
    return bypass


async def _set_org(session, org_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.current_org_id', :org, true)"),
                          {"org": str(org_id)})


async def _snapshot(session, tables: dict[str, list[dict]]) -> dict[str, list[tuple]]:
    """Every row (all columns) with the given ids, per table, read in the real org's context."""
    await _set_org(session, REAL_ORG)
    snap = {}
    for name, rows in tables.items():
        result = await session.execute(
            text(f"SELECT * FROM {name} WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": [r["id"] for r in rows]},
        )
        snap[name] = [tuple(r) for r in result.all()]
    await session.commit()
    return snap


async def _count(session, sql: str, **params) -> int:
    return (await session.execute(text(sql), params)).scalar_one()


@pytest.mark.parametrize("under_rls", [False, True], ids=["no-rls", "rls"])
async def test_reset_leaves_the_real_org_and_shared_users_untouched(setup_database, db_session,
                                                                    under_rls):
    """Without RLS the reset's own WHERE clauses are the only protection (catches a
    mis-scoped DELETE); with RLS it must still work and still touch nothing else."""
    session = db_session

    # 1. RBAC seed roles + the demo tenant, via the real seed.
    await _ensure_rbac_seed_roles(session)
    seed_plan = build_plan(today=TODAY)
    await apply_plan(session, seed_plan, SEED_HASH)
    await session.commit()

    # 2. A real org with data in every table the seed writes.
    real = _real_org_rows()
    for name in TABLE_ORDER:
        await _insert(session, name, real[name])

    # 3. Users who are members of BOTH orgs: one whose home is the real org, and one whose
    #    home is the demo org (e.g. created there) who is also a member of the real org.
    shared_user = real["users"][0]["id"]
    shared_membership = {"id": uuid.uuid4(), "user_id": shared_user, "organization_id": DEMO_ORG_ID,
                         "status": MembershipStatus.ACTIVE, "is_default": False}
    shared_role = {"id": uuid.uuid4(), "user_id": shared_user, "role_id": _id("role", "admin"),
                   "clinic_id": DEMO_CLINIC_ID}
    await _insert(session, "memberships", [shared_membership])
    await _insert(session, "user_roles", [shared_role])
    demo_home = {**seed_plan.tables["users"][0], "id": uuid.uuid4(),
                 "email": "both-orgs@demo.example.com", "hashed_password": "own-hash"}
    demo_home_membership = {"id": uuid.uuid4(), "user_id": demo_home["id"],
                            "organization_id": DEMO_ORG_ID, "status": MembershipStatus.ACTIVE,
                            "is_default": True}
    await _insert(session, "users", [demo_home])
    await _insert(session, "memberships", [demo_home_membership])
    real["memberships"].append({"id": uuid.uuid4(), "user_id": demo_home["id"],
                                "organization_id": REAL_ORG, "status": MembershipStatus.ACTIVE,
                                "is_default": False})
    await _insert(session, "memberships", real["memberships"][-1:])

    # 4. Rows a demo visitor created: a patient and a staff account (demo org only).
    await session.execute(text(f"SET LOCAL app.current_org_id = '{DEMO_ORG_ID}'"))
    visitor_patient = {**seed_plan.tables["patients"][0], "id": uuid.uuid4(),
                       "uhid": "DEMO-VISITOR-1", "phone": "+919000099999"}
    visitor_user = {**seed_plan.tables["users"][0], "id": uuid.uuid4(),
                    "email": "visitor@demo.example.com", "hashed_password": "visitor-hash"}
    await _insert(session, "patients", [visitor_patient])
    await _insert(session, "users", [visitor_user])
    await _insert(session, "memberships", [{"id": uuid.uuid4(), "user_id": visitor_user["id"],
                                            "organization_id": DEMO_ORG_ID,
                                            "status": MembershipStatus.ACTIVE,
                                            "is_default": True}])
    await _insert(session, "user_roles", [{"id": uuid.uuid4(), "user_id": visitor_user["id"],
                                           "role_id": _id("role", "admin"),
                                           "clinic_id": DEMO_CLINIC_ID}])
    await session.commit()

    needs_probe = False
    if under_rls:
        needs_probe = await _apply_rls_and_probe_role(session)
        await session.commit()

    real_before = await _snapshot(session, real)
    assert all(real_before[name] for name in TABLE_ORDER), "real org fixture is incomplete"

    # 5. The reset itself (with RLS: as a role RLS applies to).
    if needs_probe:
        await session.execute(text(f"SET LOCAL ROLE {PROBE_ROLE}"))
    outcome = await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    await session.commit()
    assert outcome["deleted"]["patients"] == len(seed_plan.tables["patients"]) + 1

    # Every real-org row is unchanged (same rows, same values).
    assert await _snapshot(session, real) == real_before

    # The shared users, their demo memberships and demo role survive.
    for user_id in (shared_user, demo_home["id"]):
        assert await _count(session, "SELECT count(*) FROM users WHERE id = :u", u=user_id) == 1
    for membership in (shared_membership, demo_home_membership):
        assert await _count(session, "SELECT count(*) FROM memberships WHERE id = :m",
                            m=membership["id"]) == 1
    assert await _count(session, "SELECT count(*) FROM user_roles WHERE id = :r",
                        r=shared_role["id"]) == 1

    # The visitor's rows are gone.
    await _set_org(session, DEMO_ORG_ID)
    assert await _count(session, "SELECT count(*) FROM patients WHERE id = :p",
                        p=visitor_patient["id"]) == 0
    for table, col in (("users", "id"), ("memberships", "user_id"), ("user_roles", "user_id")):
        assert await _count(session, f"SELECT count(*) FROM {table} WHERE {col} = :u",
                            u=visitor_user["id"]) == 0, table

    # The demo org is back to exactly the seeded rows.
    for table in ("patients", "appointments", "encounters", "invoices", "payments", "doctors"):
        assert await _count(session, f"SELECT count(*) FROM {table} WHERE organization_id = :o",
                            o=DEMO_ORG_ID) == len(seed_plan.tables[table]), table
    # Seeded staff + the user who is also a member of the real org.
    assert await _count(session, "SELECT count(*) FROM users WHERE organization_id = :o",
                        o=DEMO_ORG_ID) == len(seed_plan.tables["users"]) + 1
