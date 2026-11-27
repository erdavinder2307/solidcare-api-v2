"""enable Postgres Row-Level Security on the clinical and billing child tables

Revision ID: 6af0e2a19288
Revises: 9e1af696a1be
Create Date: 2026-11-27 00:00:00.000000

Extends migration b2c3d4e5f6a7 (patients, encounters, invoices, payments,
appointments) to the child tables that have no `organization_id` of their own:

    diagnoses, vitals, lab_orders        -> scoped by encounters.organization_id
    lab_order_items, lab_results         -> scoped by lab_orders -> encounters
    invoice_line_items                   -> scoped by invoices.organization_id

Each policy is an EXISTS subquery on the parent row, compared against the same
`app.current_org_id` session variable (set via `SET LOCAL` in
`get_current_user`, the demo-tenant seed/reset and the reminders job). The
parent's organization_id is checked explicitly rather than relying on the
parent's own policy, so each child policy stands on its own.

Same behaviour as b2c3d4e5f6a7:
  - FORCE ROW LEVEL SECURITY, because the app role owns these tables.
  - Unset `app.current_org_id` -> NULL comparison -> EXISTS is false for every
    row: reads/updates/deletes see nothing, INSERTs fail the WITH CHECK clause.

Indexes: every FK column used by the subqueries (diagnoses/vitals/lab_orders
.encounter_id, lab_order_items/lab_results.lab_order_id,
invoice_line_items.invoice_id) is already indexed by the initial schema, and the
parent side is a primary-key lookup, so no new indexes are added.

`prescriptions` / `prescription_items` stay out of scope (public share-token
route), as do the identity/auth tables.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "6af0e2a19288"
down_revision: Union[str, None] = "9e1af696a1be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY_NAME = "tenant_isolation"

_ORG = "current_setting('app.current_org_id', true)::uuid"

_VIA_ENCOUNTER = (
    "EXISTS (SELECT 1 FROM encounters e"
    " WHERE e.id = {table}.encounter_id AND e.organization_id = " + _ORG + ")"
)
_VIA_LAB_ORDER = (
    "EXISTS (SELECT 1 FROM lab_orders lo JOIN encounters e ON e.id = lo.encounter_id"
    " WHERE lo.id = {table}.lab_order_id AND e.organization_id = " + _ORG + ")"
)
_VIA_INVOICE = (
    "EXISTS (SELECT 1 FROM invoices i"
    " WHERE i.id = {table}.invoice_id AND i.organization_id = " + _ORG + ")"
)

# table -> policy predicate (used for both USING and WITH CHECK)
POLICY_PREDICATES = {
    "diagnoses": _VIA_ENCOUNTER.format(table="diagnoses"),
    "vitals": _VIA_ENCOUNTER.format(table="vitals"),
    "lab_orders": _VIA_ENCOUNTER.format(table="lab_orders"),
    "lab_order_items": _VIA_LAB_ORDER.format(table="lab_order_items"),
    "lab_results": _VIA_LAB_ORDER.format(table="lab_results"),
    "invoice_line_items": _VIA_INVOICE.format(table="invoice_line_items"),
}

TARGET_TABLES = list(POLICY_PREDICATES)


def policy_sql(table: str) -> str:
    predicate = POLICY_PREDICATES[table]
    return (
        f"CREATE POLICY {POLICY_NAME} ON {table}"
        f" USING ({predicate})"
        f" WITH CHECK ({predicate})"
    )


def upgrade() -> None:
    for table in TARGET_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(policy_sql(table))


def downgrade() -> None:
    for table in TARGET_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
