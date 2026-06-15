"""seed default demo clinic

Revision ID: d5f3a2b1c904
Revises: c4e8a1b2d903
Create Date: 2026-06-10 22:26:00.000000

Seeds the default demo organization clinic used by the web app (VITE_DEFAULT_CLINIC_ID).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d5f3a2b1c904"
down_revision: Union[str, None] = "c4e8a1b2d903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_CLINIC_ID = "00000000-0000-0000-0000-000000000010"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO organizations (id, name, slug, schema_name, country, subscription_plan, status, created_at, updated_at)
        VALUES (
            '{DEFAULT_ORG_ID}',
            'Solidcare Demo',
            'solidcare-demo',
            'solidcare_demo',
            'India',
            'FREE',
            'ACTIVE',
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO clinics (
            id, organization_id, name, code, clinic_type, city, state, is_active, created_at, updated_at
        )
        VALUES (
            '{DEFAULT_CLINIC_ID}',
            '{DEFAULT_ORG_ID}',
            'Solidcare Demo Clinic',
            'DEMO01',
            'GENERAL',
            'Zirakpur',
            'Punjab',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM clinics WHERE id = '{DEFAULT_CLINIC_ID}'")
