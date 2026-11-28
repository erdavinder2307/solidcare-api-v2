"""
Unit tests for the demo-tenant reset (SE-4193, D4).

Proves the reset can only ever touch the seeded demo org: it refuses any other org
before writing, and every DELETE it issues is filtered to the demo org. Statements
are compiled for Postgres against a fake session, never executed. Also covers the
password-source rules and the CLI (the only entry point: no endpoint, no Celery job).
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.core.demo_tenant.reset import (
    SEEDED_STAFF_IDS,
    DemoResetRefused,
    delete_statements,
    reset_demo_tenant,
)
from app.core.demo_tenant.seed import (
    DEMO_ORG_ID,
    DEMO_ORG_SLUG,
    SOURCE_ROLE_IDS,
    DemoConfigError,
    build_plan,
)
from scripts.reset_demo_tenant import main

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
    # No DEMO_SEED_PASSWORD_HASH configured: re-seed keeps the stored password hash.
    assert _seeded_hashes(session) == {"stored-hash"}
    assert result["seeded"]["patients"] == 50
    assert set(result["deleted"]) == {n for n, _ in delete_statements(DEMO_ORG_ID)}


def _seeded_hashes(session) -> set:
    users_insert = next(s for s in session.statements if str(s).startswith("INSERT INTO users"))
    params = users_insert.compile(dialect=postgresql.dialect()).params
    return {v for k, v in params.items() if k.startswith("hashed_password")}


async def test_reset_restores_the_configured_password_hash(monkeypatch):
    from app.config import settings
    from app.core.security.password import hash_password

    fixed = hash_password("demo-password-1")
    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", fixed)
    session = FakeSession(staff_hash="hash-set-by-a-visitor")
    await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert _seeded_hashes(session) == {fixed}  # a hijacked demo login is undone


async def test_explicit_password_hash_wins_over_the_setting(monkeypatch):
    from app.config import settings
    from app.core.security.password import hash_password

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", hash_password("demo-password-1"))
    session = FakeSession()
    await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY, password_hash="cli-hash")
    assert _seeded_hashes(session) == {"cli-hash"}


async def test_invalid_configured_hash_is_a_config_error_before_any_write(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", "not-a-bcrypt-hash")
    session = FakeSession()
    with pytest.raises(DemoConfigError, match="DEMO_SEED_PASSWORD_HASH"):
        await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert not any(s.startswith(("DELETE", "INSERT")) for s in session.sql())


async def test_unset_hash_keeps_current_password_and_warns(monkeypatch, caplog):
    from app.config import settings

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", "")
    session = FakeSession()
    with caplog.at_level("WARNING", logger="app.core.demo_tenant.reset"):
        await reset_demo_tenant(session, DEMO_ORG_ID, today=TODAY)
    assert _seeded_hashes(session) == {"stored-hash"}
    assert "DEMO_SEED_PASSWORD_HASH is not set" in caplog.text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def no_password_env(monkeypatch):
    from app.config import settings

    monkeypatch.delenv("DEMO_SEED_PASSWORD", raising=False)
    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", "")


def test_cli_dry_run_needs_no_db(capsys, no_password_env):
    with patch("scripts.reset_demo_tenant.run_reset") as run:
        assert main(["--dry-run"]) == 0
    run.assert_not_called()
    out = capsys.readouterr().out
    assert "patients" in out and "Dry run" in out
    assert "DEMO_SEED_PASSWORD_HASH is not set" in out  # says where the password comes from


def test_cli_dry_run_reports_the_configured_hash(capsys, no_password_env, monkeypatch):
    from app.config import settings
    from app.core.security.password import hash_password

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", hash_password("demo-password-1"))
    with patch("scripts.reset_demo_tenant.run_reset") as run:
        assert main(["--dry-run"]) == 0
    run.assert_not_called()
    assert "restored from DEMO_SEED_PASSWORD_HASH" in capsys.readouterr().out


@pytest.mark.parametrize("args", [[], ["--dry-run"]])
def test_cli_invalid_hash_is_a_clear_config_error(capsys, no_password_env, monkeypatch, args):
    from app.config import settings

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", "not-a-bcrypt-hash")
    with patch("scripts.reset_demo_tenant.run_reset") as run:
        assert main(args) == 2
    run.assert_not_called()
    err = capsys.readouterr().err
    assert "Config error" in err and "DEMO_SEED_PASSWORD_HASH" in err and "bcrypt" in err
    assert "not-a-bcrypt-hash" not in err  # never echo the configured value


async def test_run_reset_rejects_an_invalid_hash_before_opening_a_connection(monkeypatch):
    from app.config import settings
    from app.core.demo_tenant.reset import run_reset

    monkeypatch.setattr(settings, "DEMO_SEED_PASSWORD_HASH", "not-a-bcrypt-hash")
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine:
        with pytest.raises(DemoConfigError):
            await run_reset()
    create_engine.assert_not_called()


def test_cli_rejects_a_short_password(capsys, no_password_env):
    with patch("scripts.reset_demo_tenant.run_reset") as run:
        assert main(["--password", "short"]) == 2
    run.assert_not_called()
    assert "at least 8 characters" in capsys.readouterr().err


def test_cli_reports_refusal(capsys, no_password_env):
    with patch("scripts.reset_demo_tenant.run_reset",
               AsyncMock(side_effect=DemoResetRefused("is_demo = false"))):
        assert main([]) == 1
    assert "Refused" in capsys.readouterr().err
