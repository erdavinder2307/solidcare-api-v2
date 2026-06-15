BEGIN;

INSERT INTO organizations (id, name, slug, schema_name, email, country, subscription_plan, status, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Solidcare Demo',
  'solidcare-demo',
  'solidcare_demo',
  'admin@solidcare.health',
  'India',
  'FREE',
  'ACTIVE',
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO roles (id, organization_id, name, slug, description, is_system_role, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'Super Admin',
  'superadmin',
  'Full platform access',
  true,
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

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
) ON CONFLICT (id) DO NOTHING;

INSERT INTO users (
  id, organization_id, email, first_name, last_name,
  hashed_password, status, is_superadmin, email_verified, phone_verified,
  mfa_enabled, failed_login_attempts, created_at, updated_at
)
VALUES (
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000001',
  'admin@solidcare.health',
  'Admin',
  'User',
  '$2b$12$2UWGpBlNu7HtF0QwyenHgubkl.IrFZe39FpNtHiPN2fNXmkcy8Tqm',
  'ACTIVE',
  true,
  true,
  false,
  false,
  0,
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (id, user_id, role_id, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000002',
  NOW(),
  NOW()
) ON CONFLICT (id) DO NOTHING;

COMMIT;

SELECT email, status::text AS status FROM users WHERE email = 'admin@solidcare.health';
