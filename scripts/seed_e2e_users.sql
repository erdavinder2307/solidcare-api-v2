-- E2E test users for role-based testing (local/CI only — see tests/test-data/users.ts)
-- Prefer scripts/seed_dev_rbac_users.sql (upserts passwords/roles on re-run).
BEGIN;

INSERT INTO users (
  id, organization_id, email, first_name, last_name,
  hashed_password, status, is_superadmin, email_verified, phone_verified,
  mfa_enabled, failed_login_attempts, created_at, updated_at
)
VALUES
  (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'doctor@solidcare.health',
    'Demo', 'Doctor',
    '$2b$12$2UWGpBlNu7HtF0QwyenHgubkl.IrFZe39FpNtHiPN2fNXmkcy8Tqm',
    'ACTIVE', false, true, false, false, 0, NOW(), NOW()
  ),
  (
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000001',
    'receptionist@solidcare.health',
    'Demo', 'Receptionist',
    '$2b$12$2UWGpBlNu7HtF0QwyenHgubkl.IrFZe39FpNtHiPN2fNXmkcy8Tqm',
    'ACTIVE', false, true, false, false, 0, NOW(), NOW()
  ),
  (
    '00000000-0000-0000-0000-000000000012',
    '00000000-0000-0000-0000-000000000001',
    'billing@solidcare.health',
    'Demo', 'Billing',
    '$2b$12$2UWGpBlNu7HtF0QwyenHgubkl.IrFZe39FpNtHiPN2fNXmkcy8Tqm',
    'ACTIVE', false, true, false, false, 0, NOW(), NOW()
  ),
  (
    '00000000-0000-0000-0000-000000000013',
    '00000000-0000-0000-0000-000000000001',
    'orgadmin@solidcare.health',
    'Demo', 'OrgAdmin',
    '$2b$12$2UWGpBlNu7HtF0QwyenHgubkl.IrFZe39FpNtHiPN2fNXmkcy8Tqm',
    'ACTIVE', false, true, false, false, 0, NOW(), NOW()
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (id, user_id, role_id, clinic_id, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000020', '00000000-0000-0000-0000-000000000010', '00000000-0000-0020-0000-000000000002', '00000000-0000-0000-0000-000000000010', NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000021', '00000000-0000-0000-0000-000000000011', '00000000-0000-0020-0000-000000000003', '00000000-0000-0000-0000-000000000010', NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000022', '00000000-0000-0000-0000-000000000012', '00000000-0000-0020-0000-000000000004', '00000000-0000-0000-0000-000000000010', NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000023', '00000000-0000-0000-0000-000000000013', '00000000-0000-0020-0000-000000000001', '00000000-0000-0000-0000-000000000010', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO doctors (id, organization_id, user_id, registration_number, status, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000030',
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000010',
  'E2E-DOC-001',
  'ACTIVE',
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO doctor_clinic_assignments (id, doctor_id, clinic_id, is_primary, is_active, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000031',
  '00000000-0000-0000-0000-000000000030',
  '00000000-0000-0000-0000-000000000010',
  true,
  true,
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

COMMIT;
