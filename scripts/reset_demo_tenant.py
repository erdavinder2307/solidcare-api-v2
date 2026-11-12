"""Reset the public demo tenant to its seeded state (SE-4193, D4).

Deletes the demo org's data rows (patients and everything hanging off them,
appointments, encounters, prescriptions, invoices, payments, notifications,
doctors, service charges and staff accounts that visitors created) and then
re-runs the demo seed (scripts/seed_demo_tenant.py), all in ONE transaction.

Safety:
- Only the seeded demo org (DEMO_ORG_ID) can be reset, and only when it exists
  and has ``is_demo = TRUE``. The check runs before any write.
- Every DELETE is filtered by ``organization_id = <demo org>``, directly or
  through a parent row of the demo org (e.g. prescription_items → prescriptions
  → patients of the demo org). Nothing is deleted by cascade.
- Never deleted: the organization row, its clinic and roles (the seed upserts
  them), roles of other orgs, permissions, audit logs, the seeded staff logins,
  superadmins, and any user who also has a membership in another org.
- Runs with the demo org's RLS context (SET LOCAL app.current_org_id) and an
  advisory lock, so a nightly run and an on-demand reset cannot interleave.
- The staff password is kept: the seeded admin's current password hash is
  reused, unless ``--password`` / DEMO_SEED_PASSWORD gives a new one.

Usage (from the repo root, with DATABASE_URL pointing at the target database):

    python -m scripts.reset_demo_tenant --dry-run   # list what would be cleared, no DB
    python -m scripts.reset_demo_tenant

Also run nightly by the Celery beat entry "demo-tenant-reset-nightly" and on
demand by POST /api/v1/organizations/current/demo-reset (demo org admin only).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date
from typing import Any

from sqlalchemy import and_, bindparam, column, delete, exists, not_, select, table, text

from scripts.seed_demo_tenant import (
    DEMO_ORG_ID,
    DEMO_ORG_SLUG,
    PASSWORD_ENV,
    STAFF,
    _id,
    apply_plan,
    build_plan,
    validate_plan,
)

ADVISORY_LOCK_KEY = 41930004  # any constant; serialises concurrent demo resets
SEEDED_STAFF_IDS = [_id("user", key) for key, *_ in STAFF]  # admin first


class DemoResetRefused(RuntimeError):
    """The target org is not the demo tenant (or is not ready to be reset)."""


# Lightweight table stubs: no ORM mapper registry needed (works in Celery workers).
def _t(name: str, *cols: str):
    return table(name, *(column(c) for c in ("id", *cols)))


patients = _t("patients", "organization_id")
appointments = _t("appointments", "organization_id")
encounters = _t("encounters", "organization_id")
invoices = _t("invoices", "organization_id")
invoice_line_items = _t("invoice_line_items", "invoice_id")
payments = _t("payments", "organization_id")
notifications = _t("notifications", "organization_id")
prescriptions = _t("prescriptions", "patient_id")
prescription_items = _t("prescription_items", "prescription_id")
diagnoses = _t("diagnoses", "patient_id")
vitals = _t("vitals", "patient_id")
lab_orders = _t("lab_orders", "patient_id")
lab_order_items = _t("lab_order_items", "lab_order_id")
lab_results = _t("lab_results", "patient_id")
patient_consents = _t("patient_consents", "patient_id")
patient_documents = _t("patient_documents", "patient_id")
clinics = _t("clinics", "organization_id")
service_charge_master = _t("service_charge_master", "clinic_id")
doctors = _t("doctors", "organization_id")
doctor_schedules = _t("doctor_schedules", "doctor_id")
doctor_clinic_assignments = _t("doctor_clinic_assignments", "doctor_id")
users = _t("users", "organization_id", "is_superadmin")
memberships = _t("memberships", "organization_id", "user_id")
user_roles = _t("user_roles", "user_id")


def delete_statements(org_id: uuid.UUID) -> list[tuple[str, Any]]:
    """(table, DELETE) pairs in foreign-key order, every one scoped to ``org_id``."""
    demo_patients = select(patients.c.id).where(patients.c.organization_id == org_id)
    demo_invoices = select(invoices.c.id).where(invoices.c.organization_id == org_id)
    demo_doctors = select(doctors.c.id).where(doctors.c.organization_id == org_id)
    demo_clinics = select(clinics.c.id).where(clinics.c.organization_id == org_id)
    demo_prescriptions = select(prescriptions.c.id).where(
        prescriptions.c.patient_id.in_(demo_patients))
    demo_lab_orders = select(lab_orders.c.id).where(lab_orders.c.patient_id.in_(demo_patients))
    # Accounts visitors created in the demo org (e.g. POST /doctors/register). Aliases
    # keep these subqueries independent of the DELETE target table.
    u, m = users.alias("visitor_user"), memberships.alias("other_membership")
    other_org_member = exists().where(
        m.c.user_id == u.c.id, m.c.organization_id != org_id).correlate(u)
    visitor_users = select(u.c.id).where(
        u.c.organization_id == org_id,
        u.c.id.not_in(SEEDED_STAFF_IDS),
        not_(u.c.is_superadmin.is_(True)),
        not_(other_org_member),
    )

    def by(tbl, col: str, sub) -> tuple[str, Any]:
        return tbl.name, delete(tbl).where(tbl.c[col].in_(sub))

    def org(tbl) -> tuple[str, Any]:
        return tbl.name, delete(tbl).where(tbl.c.organization_id == org_id)

    return [
        by(lab_results, "patient_id", demo_patients),
        by(lab_order_items, "lab_order_id", demo_lab_orders),
        by(lab_orders, "patient_id", demo_patients),
        by(vitals, "patient_id", demo_patients),
        by(diagnoses, "patient_id", demo_patients),
        by(prescription_items, "prescription_id", demo_prescriptions),
        by(prescriptions, "patient_id", demo_patients),
        by(invoice_line_items, "invoice_id", demo_invoices),
        org(payments),
        org(invoices),
        org(notifications),
        org(encounters),
        org(appointments),
        by(patient_consents, "patient_id", demo_patients),
        by(patient_documents, "patient_id", demo_patients),
        org(patients),
        by(service_charge_master, "clinic_id", demo_clinics),
        by(doctor_schedules, "doctor_id", demo_doctors),
        by(doctor_clinic_assignments, "doctor_id", demo_doctors),
        org(doctors),
        by(user_roles, "user_id", visitor_users),
        ("memberships", delete(memberships).where(and_(
            memberships.c.organization_id == org_id,
            memberships.c.user_id.in_(visitor_users)))),
        ("users", delete(users).where(users.c.id.in_(visitor_users))),
    ]


async def _check_demo_org(session: Any, org_id: uuid.UUID) -> None:
    if org_id != DEMO_ORG_ID:
        raise DemoResetRefused(f"organization {org_id} is not the seeded demo tenant")
    result = await session.execute(
        text("SELECT is_demo FROM organizations WHERE id = :id"), {"id": org_id})
    row = result.first()
    if row is None:
        raise DemoResetRefused(f"demo organization {org_id} does not exist; run the seed first")
    if row[0] is not True:
        raise DemoResetRefused(f"organization {org_id} has is_demo = false; refusing to reset it")


async def _current_password_hash(session: Any, org_id: uuid.UUID) -> str:
    result = await session.execute(
        text("SELECT id, hashed_password FROM users WHERE organization_id = :org "
             "AND id IN :ids AND hashed_password IS NOT NULL").bindparams(
            bindparam("ids", expanding=True)),
        {"org": org_id, "ids": SEEDED_STAFF_IDS},
    )
    hashes = dict(result.all())
    for user_id in SEEDED_STAFF_IDS:
        if hashes.get(user_id):
            return hashes[user_id]
    raise DemoResetRefused("no seeded demo staff login found; run scripts.seed_demo_tenant first")


async def reset_demo_tenant(session: Any, org_id: uuid.UUID = DEMO_ORG_ID, *,
                            today: date | None = None,
                            password_hash: str | None = None) -> dict[str, Any]:
    """Clear the demo org's data and re-seed it, in the caller's transaction.

    Raises DemoResetRefused (before any write) unless ``org_id`` is the seeded
    demo org and it exists with ``is_demo = TRUE``.
    """
    org_id = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    await _check_demo_org(session, org_id)
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
    await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
    if password_hash is None:
        password_hash = await _current_password_hash(session, org_id)

    deleted: dict[str, int] = {}
    for name, stmt in delete_statements(org_id):
        result = await session.execute(stmt)
        deleted[name] = getattr(result, "rowcount", 0) or 0

    plan = build_plan(today=today)
    validate_plan(plan)
    await apply_plan(session, plan, password_hash)
    return {"deleted": deleted, "seeded": plan.counts()}


async def run_reset(password: str | None = None) -> dict[str, Any]:
    """Open a short-lived engine (safe under Celery's per-task event loop) and reset."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    password_hash = None
    if password:
        from app.core.security.password import hash_password
        password_hash = hash_password(password)

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                return await reset_demo_tenant(session, DEMO_ORG_ID,
                                               password_hash=password_hash)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="list the tables that would be cleared; no database access")
    parser.add_argument("--password", help=f"new staff password (default: keep the current "
                                           f"one, or ${PASSWORD_ENV} when set)")
    args = parser.parse_args(argv)

    print(f"Demo tenant {DEMO_ORG_SLUG} ({DEMO_ORG_ID}):")
    if args.dry_run:
        print("Would delete demo-org rows from:")
        for name, _ in delete_statements(DEMO_ORG_ID):
            print(f"  {name}")
        print("then re-run the demo seed. Dry run: nothing written.")
        return 0

    password = args.password or os.environ.get(PASSWORD_ENV)
    if password is not None and len(password) < 8:
        print(f"{PASSWORD_ENV} / --password must be at least 8 characters.", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(run_reset(password))
    except DemoResetRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    print("Deleted:")
    for name, count in result["deleted"].items():
        print(f"  {name:<28}{count:>5}")
    print("Re-seeded:")
    for name, count in result["seeded"].items():
        print(f"  {name:<28}{count:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
