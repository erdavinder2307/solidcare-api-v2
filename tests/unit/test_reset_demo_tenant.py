"""
Unit tests for the demo-tenant reset (SE-4193, D4).

Proves the reset can only ever touch the seeded demo org: it refuses any other org
before writing, and every DELETE it issues is filtered to the demo org. Statements
are compiled for Postgres against a fake session, never executed. Also covers the
admin-only "Reset demo data" endpoint, the nightly Celery beat entry and the CLI.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from scripts.reset_demo_tenant import (
    SEEDED_STAFF_IDS,
    DemoResetRefused,
    delete_statements,
    main,
    reset_demo_tenant,
)
from scripts.seed_demo_tenant import DEMO_ORG_ID, DEMO_ORG_SLUG, SOURCE_ROLE_IDS, build_plan

TODAY = date(2026, 11, 12)
OTHER_ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")  # the default (real) org
NEVER_DELETED = {"organizations", "roles", "role_permissions", "permissions", "clinics",
                 "audit_logs", "medicines", "icd10_codes"}


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _uuid_params(stmt) -> set[uuid.UUID]:
    found: set[uuid.UUID] = set()
    for value in stmt.compile(dialect=postgresql.dialect()).params.values():
        values = value if isinstance(value, (list, tuple)) else [value]
        found |= {v for v in values if isinstance(v, uuid.UUID)}
    return found


class FakeSession:
    """Records every statement; answers the few SELECTs the reset and seed make."""

    def __init__(self, is_demo: bool | None = True, staff_hash: str | None = "stored-hash"):
        self.is_demo = is_demo
        self.staff_hash = staff_hash
        self.statements: list = []

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        sql = str(stmt)
        res = MagicMock()
        res.rowcount = 1
        if sql.startswith("SELECT is_demo FROM organizations"):
            res.first.return_value = None if self.is_demo is None else (self.is_demo,)
        elif sql.startswith("SELECT id, hashed_password FROM users"):
            res.all.return_value = ([(SEEDED_STAFF_IDS[0], self.staff_hash)]
                                    if self.staff_hash else [])
        elif sql.startswith("SELECT id, slug, is_demo FROM organizations"):
            res.all.return_value = [(DEMO_ORG_ID, DEMO_ORG_SLUG, self.is_demo)]
        elif sql.startswith("SELECT role_id, permission_id FROM role_permissions"):
            res.all.return_value = [(rid, uuid.uuid4()) for rid in SOURCE_ROLE_IDS.values()]
        return res

    def sql(self) -> list[str]:
        return [_sql(s) for s in self.statements]


# ---------------------------------------------------------------------------
# Refusals: nothing is written unless the org is the demo tenant
# ---------------------------------------------------------------------------


async def test_refuses_another_org_without_touching_the_db():
    session = FakeSession()
    with pytest.raises(DemoResetRefused, match="not the seeded demo tenant"):
        await reset_demo_tenant(session, OTHER_ORG, today=TODAY)
    assert session.statements == []


async def test_refuses_demo_id_when_is_demo_is_false():
    session = FakeSession(is_demo=False)
    with pytest.raises(DemoResetRefused, match="is_demo = false"):
        await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert len(session.statements) == 1  # only the lookup ran


async def test_refuses_when_demo_org_missing():
    session = FakeSession(is_demo=None)
    with pytest.raises(DemoResetRefused, match="does not exist"):
        await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert len(session.statements) == 1


async def test_refuses_before_deleting_when_never_seeded():
    session = FakeSession(staff_hash=None)
    with pytest.raises(DemoResetRefused, match="seed"):
        await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert not any(s.startswith("DELETE") for s in session.sql())


# ---------------------------------------------------------------------------
# Every DELETE is scoped to the demo org
# ---------------------------------------------------------------------------


def test_every_delete_is_filtered_to_the_demo_org():
    for name, stmt in delete_statements(DEMO_ORG_ID):
        sql = _sql(stmt)
        assert sql.startswith(f"DELETE FROM {name} WHERE"), name
        assert "organization_id =" in sql, f"{name} delete is not scoped by org"
        params = _uuid_params(stmt)
        assert DEMO_ORG_ID in params, name
        # The only other ids allowed are the seeded staff logins (kept, never deleted).
        assert params <= {DEMO_ORG_ID, *SEEDED_STAFF_IDS}, name
        assert OTHER_ORG not in params


def test_shared_tables_are_never_deleted_from():
    names = {name for name, _ in delete_statements(DEMO_ORG_ID)}
    assert not names & NEVER_DELETED
    assert {"patients", "appointments", "encounters", "prescriptions", "invoices",
            "payments"} <= names


def test_users_who_belong_to_another_org_are_kept():
    stmts = dict(delete_statements(DEMO_ORG_ID))
    for name in ("users", "memberships", "user_roles"):
        sql = _sql(stmts[name])
        assert "other_membership.organization_id !=" in sql  # other-org members excluded
        assert "visitor_user.id NOT IN" in sql  # seeded staff excluded
        assert "is_superadmin" in sql
    assert "memberships.organization_id =" in _sql(stmts["memberships"])


def test_seeded_staff_ids_match_the_seed():
    plan = build_plan(today=TODAY)
    assert {u["id"] for u in plan.tables["users"]} == set(SEEDED_STAFF_IDS)


async def test_reset_runs_in_rls_context_then_deletes_then_reseeds():
    session = FakeSession()
    result = await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    sql = session.sql()
    rls_at = next(i for i, s in enumerate(sql) if "SET LOCAL app.current_org_id" in s)
    assert str(DEMO_ORG_ID) in sql[rls_at]
    assert any("pg_advisory_xact_lock" in s for s in sql[:rls_at])
    deletes = [i for i, s in enumerate(sql) if s.startswith("DELETE")]
    inserts = [i for i, s in enumerate(sql) if s.startswith("INSERT")]
    assert deletes and inserts and rls_at < min(deletes) and max(deletes) < min(inserts)
    for i in deletes:
        assert _uuid_params(session.statements[i]) <= {DEMO_ORG_ID, *SEEDED_STAFF_IDS}
        assert DEMO_ORG_ID in _uuid_params(session.statements[i])
    assert not any(s.startswith(("DELETE FROM organizations", "DELETE FROM roles"))
                   for s in sql)
    # Re-seed keeps the stored password hash.
    users_insert = next(s for s in session.statements if str(s).startswith("INSERT INTO users"))
    params = users_insert.compile(dialect=postgresql.dialect()).params
    assert {v for k, v in params.items() if k.startswith("hashed_password")} == {"stored-hash"}
    assert result["seeded"]["patients"] == 50
    assert set(result["deleted"]) == {n for n, _ in delete_statements(DEMO_ORG_ID)}


# ---------------------------------------------------------------------------
# "Reset demo data" endpoint
# ---------------------------------------------------------------------------


def _endpoint_app(user, is_demo: bool):
    from app.core.exceptions.errors import SolidcareException
    from app.core.exceptions.handlers import solidcare_exception_handler
    from app.database import get_db
    from app.modules.auth.dependencies import get_current_user
    from app.modules.organizations.router import router

    session = MagicMock()
    lookup = MagicMock()
    lookup.scalar_one_or_none.return_value = is_demo
    session.execute = AsyncMock(return_value=lookup)

    async def _db():
        yield session

    app = FastAPI()
    app.add_exception_handler(SolidcareException, solidcare_exception_handler)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db
    return app


def _user(org_id: uuid.UUID, roles: list[str]):
    from app.modules.auth.dependencies import CurrentUser

    return CurrentUser(user_id=uuid.uuid4(), email="x@demo.example.com", org_id=org_id,
                       clinic_ids=[], permissions=[], roles=roles)


async def _post(user, is_demo: bool):
    reset = AsyncMock(return_value={"deleted": {"patients": 3}, "seeded": {"patients": 50}})
    with patch("scripts.reset_demo_tenant.reset_demo_tenant", reset):
        transport = ASGITransport(app=_endpoint_app(user, is_demo))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/organizations/current/demo-reset")
    return resp, reset


async def test_endpoint_403_for_non_admin_in_demo_org():
    resp, reset = await _post(_user(DEMO_ORG_ID, ["doctor"]), is_demo=True)
    assert resp.status_code == 403
    reset.assert_not_awaited()


async def test_endpoint_403_for_admin_of_a_real_org():
    resp, reset = await _post(_user(OTHER_ORG, ["admin"]), is_demo=False)
    assert resp.status_code == 403
    assert "demo clinic" in resp.json()["detail"]
    reset.assert_not_awaited()


async def test_endpoint_resets_for_demo_admin():
    resp, reset = await _post(_user(DEMO_ORG_ID, ["admin"]), is_demo=True)
    assert resp.status_code == 200
    assert resp.json()["status"] == "reset"
    assert reset.await_args.args[1] == DEMO_ORG_ID


def test_demo_guard_lets_the_reset_post_through():
    from app.core.middleware.demo_guard import is_destructive

    assert not is_destructive("POST", "/api/v1/organizations/current/demo-reset")


# ---------------------------------------------------------------------------
# Nightly beat entry and task
# ---------------------------------------------------------------------------


def test_nightly_beat_entry_points_at_the_registered_task():
    from celery.schedules import crontab

    from app.core.background.celery_app import celery_app
    from app.core.background.tasks.demo_tasks import RESET_TASK_NAME

    entry = celery_app.conf.beat_schedule["demo-tenant-reset-nightly"]
    assert entry["task"] == RESET_TASK_NAME
    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].hour == {3}
    assert RESET_TASK_NAME in celery_app.tasks
    assert "app.core.background.tasks.demo_tasks" in celery_app.conf.include


def test_task_reports_skipped_when_refused():
    from app.core.background.tasks.demo_tasks import reset_demo_tenant_nightly

    with patch("scripts.reset_demo_tenant.run_reset",
               AsyncMock(side_effect=DemoResetRefused("no demo org"))):
        assert reset_demo_tenant_nightly.run()["status"] == "skipped"


def test_task_resets():
    from app.core.background.tasks.demo_tasks import reset_demo_tenant_nightly

    with patch("scripts.reset_demo_tenant.run_reset",
               AsyncMock(return_value={"deleted": {}, "seeded": {}})):
        assert reset_demo_tenant_nightly.run()["status"] == "reset"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_needs_no_db(capsys):
    with patch("scripts.reset_demo_tenant.run_reset") as run:
        assert main(["--dry-run"]) == 0
    run.assert_not_called()
    out = capsys.readouterr().out
    assert "patients" in out and "Dry run" in out


def test_cli_reports_refusal(capsys, monkeypatch):
    monkeypatch.delenv("DEMO_SEED_PASSWORD", raising=False)
    with patch("scripts.reset_demo_tenant.run_reset",
               AsyncMock(side_effect=DemoResetRefused("is_demo = false"))):
        assert main([]) == 1
    assert "Refused" in capsys.readouterr().err
