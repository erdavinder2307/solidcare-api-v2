"""add appointment_reminders (one row per appointment + reminder kind)

Revision ID: c8a4e2f19d07
Revises: b2c3d4e5f6a7
Create Date: 2026-11-12 00:00:00.000000

SE-4194. Records every appointment reminder attempt so the scheduled job never
sends the same reminder twice: UNIQUE (appointment_id, kind, slot_date,
slot_start_time) and the job inserts (claims) the row before it calls any provider.
slot_date / slot_start_time are verbatim copies of the appointment's
appointment_date / start_time (clinic local time) at send time, so a reschedule
(same appointment row, new date/time) gets its own reminder for the new slot.

Tenant isolation follows b2c3d4e5f6a7: the table carries organization_id, has
ROW LEVEL SECURITY ENABLED + FORCED and the same `tenant_isolation` policy on
`app.current_org_id`. The reminder job sets that variable per organization
(SET LOCAL) for every transaction it runs.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8a4e2f19d07"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "appointment_reminders"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("slot_start_time", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("provider_message_id", sa.String(length=200), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "appointment_id", "kind", "slot_date", "slot_start_time",
            name="uq_appointment_reminders_appointment_kind_slot",
        ),
    )
    op.create_index(op.f("ix_appointment_reminders_organization_id"), TABLE, ["organization_id"])
    op.create_index(op.f("ix_appointment_reminders_appointment_id"), TABLE, ["appointment_id"])
    op.create_index(op.f("ix_appointment_reminders_deleted_at"), TABLE, ["deleted_at"])

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {TABLE}
        USING (organization_id = current_setting('app.current_org_id', true)::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {TABLE}")
    op.drop_index(op.f("ix_appointment_reminders_deleted_at"), table_name=TABLE)
    op.drop_index(op.f("ix_appointment_reminders_appointment_id"), table_name=TABLE)
    op.drop_index(op.f("ix_appointment_reminders_organization_id"), table_name=TABLE)
    op.drop_table(TABLE)
