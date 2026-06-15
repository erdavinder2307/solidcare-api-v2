"""add encounter attestation fields

Revision ID: f1a2b3c4d206
Revises: e7f4b3c2d105
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d206"
down_revision = "e7f4b3c2d105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "encounters",
        sa.Column("attested_by_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "encounters",
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_encounters_attested_by_id",
        "encounters",
        "users",
        ["attested_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_encounters_attested_by_id",
        "encounters",
        ["attested_by_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_encounters_attested_by_id", table_name="encounters")
    op.drop_constraint("fk_encounters_attested_by_id", "encounters", type_="foreignkey")
    op.drop_column("encounters", "attested_at")
    op.drop_column("encounters", "attested_by_id")
