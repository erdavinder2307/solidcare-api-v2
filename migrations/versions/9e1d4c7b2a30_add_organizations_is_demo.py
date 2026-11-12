"""add organizations.is_demo flag (demo tenant)

Revision ID: 9e1d4c7b2a30
Revises: b2c3d4e5f6a7
Create Date: 2026-11-12 00:00:00.000000

Marks an organization as the demo tenant (SE-4193). For a demo org the API
blocks destructive operations and suppresses every outbound message (SMS,
WhatsApp, email); see app/core/demo.py. Additive: existing orgs get FALSE.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9e1d4c7b2a30"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("organizations", "is_demo")
