"""Integration test: login → create patient → book appointment."""

import os
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")

import app.register_models  # noqa: F401
from app.core.security.password import hash_password
from app.modules.clinics.models import Clinic, ClinicType
from app.modules.organizations.models import Organization, OrganizationStatus, SubscriptionPlan
from app.modules.users.models import Role, User, UserRole, UserStatus

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CLINIC_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DOCTOR_ROLE_ID = uuid.UUID("00000000-0000-0020-0000-000000000002")
DOCTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")


async def seed_flow_data(session: AsyncSession) -> None:
    from sqlalchemy import select

    from app.modules.doctors.models import Doctor, DoctorStatus

    if await session.get(Organization, ORG_ID) is None:
        session.add(
            Organization(
                id=ORG_ID,
                name="Test Org",
                slug="test-org",
                schema_name="test_org",
                subscription_plan=SubscriptionPlan.FREE,
                status=OrganizationStatus.ACTIVE,
            )
        )
        session.add(
            Clinic(
                id=CLINIC_ID,
                organization_id=ORG_ID,
                name="Test Clinic",
                code="T001",
                clinic_type=ClinicType.GENERAL,
                is_active=True,
            )
        )
        session.add(
            Role(
                id=ROLE_ID,
                organization_id=ORG_ID,
                name="Super Admin",
                slug="superadmin",
                is_system_role=True,
            )
        )
        session.add(
            Role(
                id=DOCTOR_ROLE_ID,
                organization_id=ORG_ID,
                name="Doctor",
                slug="doctor",
                is_system_role=True,
            )
        )

    admin = await session.scalar(select(User).where(User.email == "admin@solidcare.health"))
    if admin is None:
        session.add(
            User(
                id=USER_ID,
                organization_id=ORG_ID,
                email="admin@solidcare.health",
                first_name="Admin",
                last_name="User",
                hashed_password=hash_password("Admin@1234"),
                status=UserStatus.ACTIVE,
                is_superadmin=True,
                email_verified=True,
                phone_verified=False,
                mfa_enabled=False,
            )
        )
        session.add(UserRole(user_id=USER_ID, role_id=ROLE_ID))

    if await session.get(Doctor, DOCTOR_ID) is None:
        session.add(
            Doctor(
                id=DOCTOR_ID,
                organization_id=ORG_ID,
                user_id=USER_ID,
                registration_number="REG-001",
                status=DoctorStatus.ACTIVE,
            )
        )

    await session.commit()


@pytest.mark.usefixtures("setup_database")
async def test_login_create_patient_and_appointment(client: AsyncClient, db_session: AsyncSession):
    await seed_flow_data(db_session)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@solidcare.health", "password": "Admin@1234"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    patient_resp = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": "Ravi",
            "last_name": "Kumar",
            "phone": "9876501234",
            "gender": "male",
        },
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient_id = patient_resp.json()["id"]

    today = date.today().isoformat()
    appt_resp = await client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "clinic_id": str(CLINIC_ID),
            "patient_id": patient_id,
            "doctor_id": str(DOCTOR_ID),
            "appointment_date": today,
            "start_time": "10:00",
            "appointment_type": "scheduled",
            "chief_complaint": "Fever",
        },
    )
    assert appt_resp.status_code == 201, appt_resp.text
    body = appt_resp.json()
    assert body["patient_id"] == patient_id
    assert body["token_number"] is not None

    doctor_resp = await client.post(
        "/api/v1/doctors/register",
        headers=headers,
        json={
            "email": "dr.patel@solidcare.health",
            "password": "Doctor@1234",
            "first_name": "Anita",
            "last_name": "Patel",
            "phone": "9876543210",
            "clinic_id": str(CLINIC_ID),
            "registration_number": "MCI-12345",
            "specializations": ["General Medicine"],
            "consultation_fee": 500,
        },
    )
    assert doctor_resp.status_code == 201, doctor_resp.text
    doctor_body = doctor_resp.json()
    assert doctor_body["first_name"] == "Anita"
    assert doctor_body["email"] == "dr.patel@solidcare.health"
