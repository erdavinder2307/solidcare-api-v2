"""
Unit tests for the demo-tenant seed script (SE-4193, D1).

The generator is pure, so these run without a database; the write path is exercised
against a mocked session (statements are compiled for Postgres, never executed).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.appointments.models import AppointmentStatus
from scripts.seed_demo_tenant import (
    DEMO_CLINIC_ID,
    DEMO_EMAIL_DOMAIN,
    DEMO_ORG_ID,
    DEMO_ORG_SLUG,
    DEMO_PHONE_PREFIX,
    HISTORY_DAYS,
    SOURCE_ROLE_IDS,
    UPCOMING_DAYS,
    DemoSeedRefused,
    apply_plan,
    build_plan,
    check_target_org,
    main,
    validate_plan,
)

TODAY = date(2026, 11, 12)


@pytest.fixture(scope="module")
def plan():
    return build_plan(seed=4193, today=TODAY)


def test_same_seed_gives_same_data(plan):
    assert build_plan(seed=4193, today=TODAY).tables == plan.tables


def test_different_seed_gives_different_patients(plan):
    other = build_plan(seed=1, today=TODAY)
    names = lambda p: [(r["first_name"], r["last_name"]) for r in p.tables["patients"]]  # noqa: E731
    assert names(other) != names(plan)


def test_about_fifty_patients_with_unique_ids(plan):
    patients = plan.tables["patients"]
    assert len(patients) == 50
    assert len({p["id"] for p in patients}) == 50
    assert len({p["uhid"] for p in patients}) == 50
    assert all(p["uhid"].startswith("DEMO-") for p in patients)


def test_dates_spread_over_last_six_months(plan):
    appts = plan.tables["appointments"]
    past = [a["appointment_date"] for a in appts if a["appointment_date"] < TODAY]
    assert len(past) > 100
    assert min(past) >= TODAY - timedelta(days=HISTORY_DAYS)
    assert min(past) <= TODAY - timedelta(days=150)  # history really reaches back
    assert max(a["appointment_date"] for a in appts) <= TODAY + timedelta(days=UPCOMING_DAYS + 1)
    months = {(d.year, d.month) for d in past}
    assert len(months) >= 6
    assert all(d.weekday() != 6 for d in past)  # no Sunday visits


def test_history_is_consistent(plan):
    t = plan.tables
    completed = [a for a in t["appointments"] if a["status"] == AppointmentStatus.COMPLETED]
    assert len(t["encounters"]) == len(completed) == len(t["invoices"]) == len(t["prescriptions"])
    assert {e["appointment_id"] for e in t["encounters"]} == {a["id"] for a in completed}
    assert all(a["appointment_date"] < TODAY for a in completed)
    upcoming = [a for a in t["appointments"] if a["appointment_date"] >= TODAY]
    assert upcoming and all(
        a["status"] in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED) for a in upcoming
    )
    paid = {i["id"] for i in t["invoices"] if i["paid_amount"] > 0}
    assert {p["invoice_id"] for p in t["payments"]} == paid
    assert len({i["invoice_number"] for i in t["invoices"]}) == len(t["invoices"])


def test_rows_in_a_table_share_columns(plan):
    for name, rows in plan.tables.items():
        if rows:
            assert all(r.keys() == rows[0].keys() for r in rows), name


def test_no_deliverable_email_or_real_phone(plan):
    emails = [r["email"] for rows in plan.tables.values() for r in rows if r.get("email")]
    assert len(emails) > 50
    assert all(e.endswith(f"@{DEMO_EMAIL_DOMAIN}") for e in emails)
    phones = [
        r[k] for rows in plan.tables.values() for r in rows
        for k in ("phone", "emergency_contact_phone") if r.get(k)
    ]
    assert phones and all(p.startswith(DEMO_PHONE_PREFIX) and len(p) == 13 for p in phones)


def test_org_is_demo_and_everything_is_scoped_to_it(plan):
    (org,) = plan.tables["organizations"]
    assert org["id"] == DEMO_ORG_ID and org["slug"] == DEMO_ORG_SLUG and org["is_demo"] is True
    for rows in plan.tables.values():
        for r in rows:
            if "organization_id" in r:
                assert r["organization_id"] == DEMO_ORG_ID
            if "clinic_id" in r:
                assert r["clinic_id"] == DEMO_CLINIC_ID
    assert {r["slug"] for r in plan.tables["roles"]} == set(SOURCE_ROLE_IDS)
    assert "hashed_password" not in plan.tables["users"][0]
    validate_plan(plan)


def test_validate_plan_rejects_rows_outside_demo_org(plan):
    bad = build_plan(seed=4193, today=TODAY)
    bad.tables["patients"][0]["organization_id"] = uuid.uuid4()
    with pytest.raises(DemoSeedRefused):
        validate_plan(bad)
    bad = build_plan(seed=4193, today=TODAY)
    bad.tables["organizations"][0]["is_demo"] = False
    with pytest.raises(DemoSeedRefused):
        validate_plan(bad)


def test_check_target_org():
    assert check_target_org([]) == "create"
    assert check_target_org([(DEMO_ORG_ID, DEMO_ORG_SLUG, True)]) == "refresh"
    with pytest.raises(DemoSeedRefused, match="is_demo is false"):
        check_target_org([(DEMO_ORG_ID, DEMO_ORG_SLUG, False)])
    with pytest.raises(DemoSeedRefused, match="another organization"):
        check_target_org([(uuid.uuid4(), DEMO_ORG_SLUG, True)])


def _result(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


async def test_apply_refuses_when_org_is_not_demo(plan):
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result([(DEMO_ORG_ID, DEMO_ORG_SLUG, False)]))
    with pytest.raises(DemoSeedRefused):
        await apply_plan(session, plan, "hash")
    assert session.execute.await_count == 1  # only the lookup ran, nothing was written


async def test_apply_refuses_without_rbac_seed(plan):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_result([]), _result([])])
    with pytest.raises(DemoSeedRefused, match="alembic upgrade head"):
        await apply_plan(session, plan, "hash")
    assert session.execute.await_count == 2


async def test_apply_sets_rls_context_and_upserts_every_table(plan):
    perm = uuid.uuid4()
    rbac = [(rid, perm) for rid in SOURCE_ROLE_IDS.values()]
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[_result([(DEMO_ORG_ID, DEMO_ORG_SLUG, True)]), _result(rbac)]
        + [MagicMock()] * 40
    )
    assert await apply_plan(session, plan, "hash") == "refresh"

    sql = [
        str(c.args[0].compile(dialect=postgresql.dialect()))
        for c in session.execute.await_args_list
    ]
    rls_at = next(i for i, s in enumerate(sql) if "SET LOCAL app.current_org_id" in s)
    assert str(DEMO_ORG_ID) in sql[rls_at]
    inserts = [s for s in sql[rls_at + 1:] if s.startswith("INSERT INTO")]
    tables = [s.split()[2] for s in inserts]
    assert tables[0] == "organizations" and "patients" in tables and tables[-1] == "payments"
    assert all("ON CONFLICT (id) DO UPDATE" in s for s in inserts)
    assert not any(s.lstrip().upper().startswith("DELETE") for s in sql)
    users_stmt = next(c.args[0] for c in session.execute.await_args_list
                      if str(c.args[0]).startswith("INSERT INTO users"))
    params = users_stmt.compile(dialect=postgresql.dialect()).params
    assert {v for k, v in params.items() if k.startswith("hashed_password")} == {"hash"}


def test_dry_run_needs_no_db_or_password(capsys, monkeypatch):
    monkeypatch.delenv("DEMO_SEED_PASSWORD", raising=False)
    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "patients" in out and "Dry run" in out


def test_real_run_requires_password(monkeypatch):
    monkeypatch.delenv("DEMO_SEED_PASSWORD", raising=False)
    assert main([]) == 2
