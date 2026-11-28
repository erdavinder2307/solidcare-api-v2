"""make patients.uhid unique per organization instead of globally

Revision ID: 3c7d9e2f4a18
Revises: 6af0e2a19288
Create Date: 2026-11-28 00:00:00.000000

`PatientRepository.generate_uhid` numbers patients per organization
(PT000001, PT000002, ...), so the first patient of every new organization gets
PT000001. The initial schema made `ix_patients_uhid` a GLOBAL unique index, so
that insert failed with a UniqueViolation for every organization after the
first one.

This replaces it with:
  - `uq_patients_org_uhid`: UNIQUE (organization_id, uhid)
  - `ix_patients_uhid`: the same name, now a plain (non-unique) index, kept for
    the UHID search on the patient list.

Existing data cannot violate the new constraint (globally unique values are
also unique per organization), so upgrade needs no data change.

Downgrade restores the global unique index; it fails if two organizations
already share a UHID, which is the expected state once this has run in use.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "3c7d9e2f4a18"
down_revision: Union[str, None] = "6af0e2a19288"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_patients_org_uhid", "patients", ["organization_id", "uhid"])
    op.drop_index("ix_patients_uhid", table_name="patients")
    op.create_index("ix_patients_uhid", "patients", ["uhid"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_patients_uhid", table_name="patients")
    op.create_index("ix_patients_uhid", "patients", ["uhid"], unique=True)
    op.drop_constraint("uq_patients_org_uhid", "patients", type_="unique")
