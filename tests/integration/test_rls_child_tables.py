"""Proves Row-Level Security isolates the child tables that have no organization_id.

Covers migration `6af0e2a19288`: diagnoses, vitals, lab_orders, lab_order_items,
lab_results and invoice_line_items are scoped through their parent row
(encounters / lab_orders -> encounters / invoices). Like
test_rls_tenant_isolation.py, the schema here comes from `create_all()`, not
Alembic, so the fixture applies the policy DDL itself — taken from the migration
module, so the tests exercise exactly what the migration creates.

For every table:
  1. Deny-by-default: no `app.current_org_id` -> zero rows.
  2. Correct org -> only that org's row.
  3. Wrong org -> only the other org's row, never this one.
  4. WITH CHECK: a row whose parent belongs to another org cannot be inserted.
  5. A row whose parent belongs to the session's org can be inserted.
"""

import importlib.util
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

import app.register_models  # noqa: F401
from app.modules.billing.invoices.models import Invoice, InvoiceLineItem, ServiceCategory
from app.modules.clinical.diagnoses.models import Diagnosis
from app.modules.clinical.encounters.models import Encounter
from app.modules.clinical.lab_orders.models import LabOrder, LabOrderItem, LabResult
from app.modules.clinical.vitals.models import Vital
from app.modules.clinics.models import Clinic, ClinicType
from app.modules.doctors.models import Doctor, DoctorStatus
from app.modules.organizations.models import Organization
from app.modules.patients.models import Patient
from app.modules.users.models import User, UserStatus

pytestmark = pytest.mark.asyncio

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "6af0e2a19288_enable_rls_clinical_child_tables.py"
)
_spec = importlib.util.spec_from_file_location("rls_child_tables_migration", _MIGRATION_PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

CHILD_TABLES = migration.TARGET_TABLES
PARENT_TABLES = ["encounters", "invoices"]
ORG_A = uuid.UUID("77777777-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("77777777-0000-0000-0000-00000000000b")
# Same reason as test_rls_tenant_isolation.py: superusers / BYPASSRLS roles skip RLS.
PROBE_ROLE = "rls_probe"

# Which parent each table's insert points at, and a minimal INSERT for it.
_PARENT_KEY = {
    "diagnoses": "encounter",
    "vitals": "encounter",
    "lab_orders": "encounter",
    "lab_order_items": "lab_order",
    "lab_results": "lab_order",
    "invoice_line_items": "invoice",
}
_INSERT_SQL = {
    "diagnoses": """
        INSERT INTO diagnoses (id, encounter_id, patient_id, diagnosis_type, status, is_chronic)
        VALUES (:id, :parent_id, :patient_id, 'PRIMARY', 'ACTIVE', false)
    """,
    "vitals": """
        INSERT INTO vitals (id, encounter_id, patient_id, recorded_at, temperature_unit)
        VALUES (:id, :parent_id, :patient_id, now(), 'C')
    """,
    "lab_orders": """
        INSERT INTO lab_orders (id, encounter_id, patient_id, ordered_by_id, status, ordered_at)
        VALUES (:id, :parent_id, :patient_id, :doctor_id, 'ORDERED', now())
    """,
    "lab_order_items": """
        INSERT INTO lab_order_items (id, lab_order_id, test_name)
        VALUES (:id, :parent_id, 'CBC')
    """,
    "lab_results": """
        INSERT INTO lab_results (id, lab_order_id, patient_id, test_name)
        VALUES (:id, :parent_id, :patient_id, 'CBC')
    """,
    "invoice_line_items": """
        INSERT INTO invoice_line_items
            (id, invoice_id, service_category, description, quantity, unit_price,
             discount_amount, tax_rate, tax_amount, total_amount, sort_order)
        VALUES (:id, :parent_id, 'CONSULTATION', 'Consultation', 1, 100, 0, 0, 0, 100, 0)
    """,
}


async def _seed_two_orgs(session) -> dict:
    """One full parent chain plus one row in every child table, per org.

    Returns {org_id: {"patient": id, "doctor": id, "encounter": id, "invoice": id,
    "lab_order": id, <child table>: row id, ...}}.
    """
    now = datetime.now(timezone.utc)
    ids: dict = {}
    for n, org_id in enumerate((ORG_A, ORG_B)):
        o = {k: uuid.uuid4() for k in (
            "clinic", "user", "doctor", "patient", "encounter", "invoice",
            "lab_order", "diagnoses", "vitals", "lab_order_items", "lab_results",
            "invoice_line_items",
        )}
        o["lab_orders"] = o["lab_order"]
        ids[org_id] = o
        session.add(Organization(
            id=org_id, name=f"RLS Child Org {n}", slug=f"rls-child-{org_id}",
            schema_name=f"rls_child_{org_id.hex}", country="India",
        ))
        await session.flush()
        session.add(Clinic(
            id=o["clinic"], organization_id=org_id, name=f"Clinic {n}", code=f"RC{n}",
            clinic_type=ClinicType.GENERAL, is_active=True,
        ))
        session.add(User(
            id=o["user"], organization_id=org_id, email=f"rls-child-{org_id}@example.com",
            first_name="Doc", last_name=str(n), hashed_password="x", status=UserStatus.ACTIVE,
            is_superadmin=False, email_verified=True, phone_verified=False, mfa_enabled=False,
        ))
        session.add(Patient(
            id=o["patient"], organization_id=org_id, uhid=f"UHID-RC-{uuid.uuid4().hex[:6]}",
            first_name="Child", last_name=str(n), phone=f"+91000000003{n}",
            country="India", is_active=True, is_merged=False,
        ))
        await session.flush()
        session.add(Doctor(
            id=o["doctor"], organization_id=org_id, user_id=o["user"],
            registration_number=f"REG-RC-{n}", status=DoctorStatus.ACTIVE,
        ))
        await session.flush()
        session.add(Encounter(
            id=o["encounter"], organization_id=org_id, clinic_id=o["clinic"],
            patient_id=o["patient"], doctor_id=o["doctor"], encounter_date=now,
        ))
        await session.flush()
        session.add(Invoice(
            id=o["invoice"], organization_id=org_id, clinic_id=o["clinic"],
            patient_id=o["patient"], encounter_id=o["encounter"],
            invoice_number=f"INV-RC-{uuid.uuid4().hex[:8]}", invoice_date=date.today(),
        ))
        session.add(LabOrder(
            id=o["lab_order"], encounter_id=o["encounter"], patient_id=o["patient"],
            ordered_by_id=o["doctor"], ordered_at=now,
        ))
        session.add(Diagnosis(
            id=o["diagnoses"], encounter_id=o["encounter"], patient_id=o["patient"],
            custom_description=f"Dx {n}",
        ))
        session.add(Vital(
            id=o["vitals"], encounter_id=o["encounter"], patient_id=o["patient"], recorded_at=now,
        ))
        await session.flush()
        session.add(LabOrderItem(id=o["lab_order_items"], lab_order_id=o["lab_order"], test_name="CBC"))
        session.add(LabResult(
            id=o["lab_results"], lab_order_id=o["lab_order"], patient_id=o["patient"], test_name="CBC",
        ))
        session.add(InvoiceLineItem(
            id=o["invoice_line_items"], invoice_id=o["invoice"],
            service_category=ServiceCategory.CONSULTATION, description="Consultation",
            unit_price=100.0, total_amount=100.0,
        ))
    await session.commit()
    return ids


async def _bypasses_rls(session) -> bool:
    result = await session.execute(
        text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    return result.scalar_one()


async def _apply_rls(session):
    """Applies migration 6af0e2a19288's DDL to the create_all() schema."""
    for table in CHILD_TABLES:
        await session.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        await session.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        await session.execute(text(f"DROP POLICY IF EXISTS {migration.POLICY_NAME} ON {table}"))
        await session.execute(text(migration.policy_sql(table)))
    if await _bypasses_rls(session):
        await session.execute(
            text(
                f"""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN
                        CREATE ROLE {PROBE_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END $$
                """
            )
        )
        await session.execute(text(f"GRANT SELECT, INSERT ON {', '.join(CHILD_TABLES)} TO {PROBE_ROLE}"))
        # The policies' subqueries read the parent tables with the caller's privileges.
        await session.execute(text(f"GRANT SELECT ON {', '.join(PARENT_TABLES)} TO {PROBE_ROLE}"))
    await session.commit()


async def _drop_rls_bypass(session) -> None:
    if await _bypasses_rls(session):
        await session.execute(text(f"SET LOCAL ROLE {PROBE_ROLE}"))
    assert not await _bypasses_rls(session), "test role bypasses RLS; the checks below would prove nothing"


async def _visible_ids(session, table) -> set[uuid.UUID]:
    result = await session.execute(text(f"SELECT id FROM {table}"))
    return {r[0] for r in result.all()}


async def _scoped(session, org_id: uuid.UUID | None) -> None:
    await session.execute(text("BEGIN"))
    await _drop_rls_bypass(session)
    if org_id is not None:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))


def _insert_params(ids: dict, parent_org: uuid.UUID, table: str) -> dict:
    o = ids[parent_org]
    return {
        "id": str(uuid.uuid4()),
        "parent_id": str(o[_PARENT_KEY[table]]),
        "patient_id": str(o["patient"]),
        "doctor_id": str(o["doctor"]),
    }


@pytest.fixture
async def seeded(setup_database, db_session):
    ids = await _seed_two_orgs(db_session)
    await _apply_rls(db_session)
    return ids


@pytest.mark.parametrize("table", CHILD_TABLES)
async def test_no_org_context_sees_nothing(seeded, db_session, table):
    await _scoped(db_session, None)
    assert await _visible_ids(db_session, table) == set()


@pytest.mark.parametrize("table", CHILD_TABLES)
async def test_correct_org_sees_only_its_own_row(seeded, db_session, table):
    await _scoped(db_session, ORG_A)
    assert await _visible_ids(db_session, table) == {seeded[ORG_A][table]}


@pytest.mark.parametrize("table", CHILD_TABLES)
async def test_wrong_org_does_not_see_other_orgs_row(seeded, db_session, table):
    await _scoped(db_session, ORG_B)
    visible = await _visible_ids(db_session, table)
    assert seeded[ORG_A][table] not in visible, f"Org A's {table} row visible to Org B"
    assert visible == {seeded[ORG_B][table]}


@pytest.mark.parametrize("table", CHILD_TABLES)
async def test_insert_under_other_orgs_parent_rejected(seeded, db_session, table):
    await _scoped(db_session, ORG_A)
    with pytest.raises(Exception) as exc_info:
        await db_session.execute(text(_INSERT_SQL[table]), _insert_params(seeded, ORG_B, table))
    msg = str(exc_info.value).lower()
    assert "row-level security" in msg or "policy" in msg


@pytest.mark.parametrize("table", CHILD_TABLES)
async def test_insert_under_own_parent_allowed(seeded, db_session, table):
    await _scoped(db_session, ORG_A)
    params = _insert_params(seeded, ORG_A, table)
    await db_session.execute(text(_INSERT_SQL[table]), params)
    assert uuid.UUID(params["id"]) in await _visible_ids(db_session, table)
