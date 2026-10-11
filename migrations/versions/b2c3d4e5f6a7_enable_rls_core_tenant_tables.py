"""enable Postgres Row-Level Security on the core tenant tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-15 00:00:00.000000

Defense-in-depth per docs/adr/002-shared-schema-tenancy.md: shared-schema
tenancy relies on every query correctly filtering by `organization_id`. This
migration makes that filter non-optional at the database layer for the five
highest-sensitivity tables (patient identity, clinical notes, and money):

    patients, encounters, invoices, payments, appointments

Requires `FORCE ROW LEVEL SECURITY` — the app's DB role (`solidcare`) OWNS these
tables (it ran the migrations that created them), and table owners bypass plain
`ENABLE ROW LEVEL SECURITY` entirely by default. Without FORCE, this migration
would silently do nothing while the roadmap claimed tenant isolation was hardened.

The policy compares `organization_id` to the Postgres session variable
`app.current_org_id`, set once per authenticated request in
`app/modules/auth/dependencies.py::get_current_user` via `SET LOCAL` (scoped to
the request's transaction, cleared automatically at commit/rollback — never
leaks across pooled connections).

Deliberately OUT OF SCOPE for this migration (see ROADMAP.md F6 for why each is
deferred, not forgotten):
  - Child tables with no direct `organization_id` column (diagnoses, vitals,
    lab_orders/items/results, invoice_line_items) — would need subquery-based
    policies against their parent table, a distinct verification effort.
  - `prescriptions` — has a genuinely unauthenticated public route
    (`GET /prescriptions/share/{share_token}`) that looks up across all orgs by
    design; needs a dedicated cross-org lookup pattern before RLS can apply.
  - `users`, `roles`, `permissions`, `organizations`, `memberships` — the
    identity/auth layer has its own access patterns (e.g. login must look up a
    user BEFORE any org context exists) that don't fit this simple policy.

Failure mode if `app.current_org_id` is unset for a session touching these
tables: `current_setting(..., true)` returns NULL, so the equality check is
UNKNOWN for every row — SELECT/UPDATE/DELETE see zero rows (fails closed,
silently), INSERT is rejected by the WITH CHECK clause (fails loudly, with a
policy-violation error). No Celery task currently queries these tables (all are
stubs returning a status dict), and no existing migration inserts into them
directly (verified before writing this migration) — so there is no known code
path that would break by this becoming a hard requirement.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_TABLES = ["patients", "encounters", "invoices", "payments", "appointments"]

POLICY_NAME = "tenant_isolation"

_POLICY_SQL = f"""
    CREATE POLICY {POLICY_NAME} ON {{table}}
    USING (organization_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
"""


def upgrade() -> None:
    for table in TARGET_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_POLICY_SQL.format(table=table))


def downgrade() -> None:
    for table in TARGET_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
