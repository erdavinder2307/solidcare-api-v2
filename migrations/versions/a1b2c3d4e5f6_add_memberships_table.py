"""add memberships table (user <-> org N:M) with backfill

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d206
Create Date: 2026-08-12 00:00:00.000000

Introduces `memberships`, replacing the implicit 1:1 relationship enforced by
`users.organization_id NOT NULL`. This migration is purely additive:
`users.organization_id` is untouched and remains the source of truth for any
code that has not yet been migrated to read memberships (see ROADMAP.md F1/F2).

Backfill: one ACTIVE, is_default=True membership per existing user, derived
from their current `organization_id`. Idempotent — safe to re-run via
ON CONFLICT DO NOTHING against the (user_id, organization_id) unique constraint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# NOTE: enum labels are the Python Enum *member names* (uppercase), matching
# SQLAlchemy's default `Enum(PyEnum)` binding used everywhere else in this codebase
# (e.g. InvoiceStatus: DRAFT/ISSUED/PAID, not draft/issued/paid).
membership_status = postgresql.ENUM(
    "ACTIVE", "INVITED", "SUSPENDED", name="membershipstatus", create_type=False
)


def upgrade() -> None:
    membership_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", membership_status, nullable=False, server_default="ACTIVE"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_deleted_at", "memberships", ["deleted_at"])

    # Backfill: one membership per existing user, from their current org.
    op.execute(
        """
        INSERT INTO memberships (id, user_id, organization_id, status, is_default, created_at, updated_at)
        SELECT gen_random_uuid(), u.id, u.organization_id, 'ACTIVE', true, now(), now()
        FROM users u
        WHERE u.organization_id IS NOT NULL
        ON CONFLICT (user_id, organization_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_memberships_deleted_at", table_name="memberships")
    op.drop_index("ix_memberships_organization_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")
    membership_status.drop(op.get_bind(), checkfirst=True)
