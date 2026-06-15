"""seed rbac permissions and roles

Revision ID: c4e8a1b2d903
Revises: bd2c78fe0918
Create Date: 2026-06-10 18:30:00.000000

Seeds system permissions, default roles, and role-permission mappings for the
default demo organization. Safe to re-run (uses ON CONFLICT DO NOTHING).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c4e8a1b2d903"
down_revision: Union[str, None] = "bd2c78fe0918"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

# role ids
ROLE_SUPERADMIN = "00000000-0000-0000-0000-000000000002"
ROLE_ADMIN = "00000000-0000-0020-0000-000000000001"
ROLE_DOCTOR = "00000000-0000-0020-0000-000000000002"
ROLE_RECEPTIONIST = "00000000-0000-0020-0000-000000000003"
ROLE_BILLING_CLERK = "00000000-0000-0020-0000-000000000004"

PERMISSIONS: list[tuple[str, str, str, str, str]] = [
    # (id, slug, name, resource, action)
    ("00000000-0000-0010-0001-000000000001", "patient:create", "Create Patient", "patient", "create"),
    ("00000000-0000-0010-0001-000000000002", "patient:read", "Read Patient", "patient", "read"),
    ("00000000-0000-0010-0001-000000000003", "patient:update", "Update Patient", "patient", "update"),
    ("00000000-0000-0010-0001-000000000004", "patient:delete", "Delete Patient", "patient", "delete"),
    ("00000000-0000-0010-0001-000000000005", "doctor:create", "Create Doctor", "doctor", "create"),
    ("00000000-0000-0010-0001-000000000006", "doctor:read", "Read Doctor", "doctor", "read"),
    ("00000000-0000-0010-0001-000000000007", "doctor:update", "Update Doctor", "doctor", "update"),
    ("00000000-0000-0010-0001-000000000008", "appointment:create", "Create Appointment", "appointment", "create"),
    ("00000000-0000-0010-0001-000000000009", "appointment:read", "Read Appointment", "appointment", "read"),
    ("00000000-0000-0010-0001-000000000010", "appointment:update", "Update Appointment", "appointment", "update"),
    ("00000000-0000-0010-0001-000000000011", "encounter:create", "Create Encounter", "encounter", "create"),
    ("00000000-0000-0010-0001-000000000012", "encounter:read", "Read Encounter", "encounter", "read"),
    ("00000000-0000-0010-0001-000000000013", "encounter:update", "Update Encounter", "encounter", "update"),
    ("00000000-0000-0010-0001-000000000014", "prescription:create", "Create Prescription", "prescription", "create"),
    ("00000000-0000-0010-0001-000000000015", "prescription:read", "Read Prescription", "prescription", "read"),
    ("00000000-0000-0010-0001-000000000016", "prescription:update", "Update Prescription", "prescription", "update"),
    ("00000000-0000-0010-0001-000000000017", "billing:create", "Create Billing", "billing", "create"),
    ("00000000-0000-0010-0001-000000000018", "billing:read", "Read Billing", "billing", "read"),
    ("00000000-0000-0010-0001-000000000019", "notification:read", "Read Notifications", "notification", "read"),
    ("00000000-0000-0010-0001-000000000020", "report:read", "Read Reports", "report", "read"),
    ("00000000-0000-0010-0001-000000000021", "audit:read", "Read Audit Logs", "audit", "read"),
]

ALL_PERMISSION_IDS = [p[0] for p in PERMISSIONS]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    ROLE_SUPERADMIN: ALL_PERMISSION_IDS,
    ROLE_ADMIN: ALL_PERMISSION_IDS,
    ROLE_DOCTOR: [
        "00000000-0000-0010-0001-000000000002",  # patient:read
        "00000000-0000-0010-0001-000000000006",  # doctor:read
        "00000000-0000-0010-0001-000000000007",  # doctor:update
        "00000000-0000-0010-0001-000000000009",  # appointment:read
        "00000000-0000-0010-0001-000000000010",  # appointment:update
        "00000000-0000-0010-0001-000000000011",  # encounter:create
        "00000000-0000-0010-0001-000000000012",  # encounter:read
        "00000000-0000-0010-0001-000000000013",  # encounter:update
        "00000000-0000-0010-0001-000000000014",  # prescription:create
        "00000000-0000-0010-0001-000000000015",  # prescription:read
        "00000000-0000-0010-0001-000000000016",  # prescription:update
        "00000000-0000-0010-0001-000000000019",  # notification:read
        "00000000-0000-0010-0001-000000000020",  # report:read
    ],
    ROLE_RECEPTIONIST: [
        "00000000-0000-0010-0001-000000000001",  # patient:create
        "00000000-0000-0010-0001-000000000002",  # patient:read
        "00000000-0000-0010-0001-000000000003",  # patient:update
        "00000000-0000-0010-0001-000000000006",  # doctor:read
        "00000000-0000-0010-0001-000000000008",  # appointment:create
        "00000000-0000-0010-0001-000000000009",  # appointment:read
        "00000000-0000-0010-0001-000000000010",  # appointment:update
        "00000000-0000-0010-0001-000000000018",  # billing:read
        "00000000-0000-0010-0001-000000000019",  # notification:read
    ],
    ROLE_BILLING_CLERK: [
        "00000000-0000-0010-0001-000000000002",  # patient:read
        "00000000-0000-0010-0001-000000000017",  # billing:create
        "00000000-0000-0010-0001-000000000018",  # billing:read
        "00000000-0000-0010-0001-000000000020",  # report:read
    ],
}


def _insert_permissions() -> None:
    values = ",\n".join(
        f"('{pid}', '{slug}', '{name}', '{resource}', '{action}', NOW(), NOW())"
        for pid, slug, name, resource, action in PERMISSIONS
    )
    op.execute(
        f"""
        INSERT INTO permissions (id, slug, name, resource, action, created_at, updated_at)
        VALUES {values}
        ON CONFLICT (slug) DO NOTHING
        """
    )


def _insert_default_org() -> None:
    op.execute(
        f"""
        INSERT INTO organizations (id, name, slug, schema_name, email, country, subscription_plan, status, created_at, updated_at)
        VALUES (
            '{DEFAULT_ORG_ID}',
            'Solidcare Demo',
            'solidcare-demo',
            'solidcare_demo',
            'admin@solidcare.health',
            'India',
            'FREE',
            'ACTIVE',
            NOW(),
            NOW()
        ) ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO clinics (
            id, organization_id, name, code, clinic_type, city, state, is_active, created_at, updated_at
        )
        VALUES (
            '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000001',
            'Solidcare Demo Clinic',
            'DEMO01',
            'GENERAL',
            'Zirakpur',
            'Punjab',
            true,
            NOW(),
            NOW()
        ) ON CONFLICT (id) DO NOTHING
        """
    )


def _insert_roles() -> None:
    op.execute(
        f"""
        INSERT INTO roles (id, organization_id, name, slug, description, is_system_role, created_at, updated_at)
        VALUES
            ('{ROLE_SUPERADMIN}', '{DEFAULT_ORG_ID}', 'Super Admin', 'superadmin',
             'Full platform access', true, NOW(), NOW()),
            ('{ROLE_ADMIN}', '{DEFAULT_ORG_ID}', 'Organization Admin', 'admin',
             'Organization administrator with full module access', true, NOW(), NOW()),
            ('{ROLE_DOCTOR}', '{DEFAULT_ORG_ID}', 'Doctor', 'doctor',
             'Clinical staff — encounters, prescriptions, appointments', true, NOW(), NOW()),
            ('{ROLE_RECEPTIONIST}', '{DEFAULT_ORG_ID}', 'Receptionist', 'receptionist',
             'Front desk — patients and appointments', true, NOW(), NOW()),
            ('{ROLE_BILLING_CLERK}', '{DEFAULT_ORG_ID}', 'Billing Clerk', 'billing_clerk',
             'Billing and payment operations', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )


def _insert_role_permissions() -> None:
    rows: list[str] = []
    rp_id = 1
    for role_id, permission_ids in ROLE_PERMISSIONS.items():
        for permission_id in permission_ids:
            rows.append(
                f"('00000000-0000-0030-0000-{rp_id:012d}', '{role_id}', '{permission_id}', NOW(), NOW())"
            )
            rp_id += 1

    op.execute(
        f"""
        INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
        VALUES {", ".join(rows)}
        ON CONFLICT (id) DO NOTHING
        """
    )


def upgrade() -> None:
    _insert_default_org()
    _insert_permissions()
    _insert_roles()
    _insert_role_permissions()


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (
            '00000000-0000-0000-0000-000000000002',
            '00000000-0000-0020-0000-000000000001',
            '00000000-0000-0020-0000-000000000002',
            '00000000-0000-0020-0000-000000000003',
            '00000000-0000-0020-0000-000000000004'
        )
        """
    )
    op.execute(
        """
        DELETE FROM roles
        WHERE id IN (
            '00000000-0000-0020-0000-000000000001',
            '00000000-0000-0020-0000-000000000002',
            '00000000-0000-0020-0000-000000000003',
            '00000000-0000-0020-0000-000000000004'
        )
        """
    )
    permission_ids = ", ".join(f"'{pid}'" for pid in ALL_PERMISSION_IDS)
    op.execute(
        f"""
        DELETE FROM permissions
        WHERE id IN ({permission_ids})
        """
    )
