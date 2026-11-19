"""merge demo-clinic and reminders heads

Revision ID: 9e1af696a1be
Revises: 9e1d4c7b2a30, c8a4e2f19d07
Create Date: 2026-11-19 11:27:22.031827

Merge-only revision: 9e1d4c7b2a30 (organizations.is_demo) and c8a4e2f19d07
(appointment_reminders) were both added on b2c3d4e5f6a7, leaving two heads.
No schema changes.
"""

from typing import Sequence, Union

revision: str = "9e1af696a1be"
down_revision: Union[str, Sequence[str], None] = ("9e1d4c7b2a30", "c8a4e2f19d07")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
