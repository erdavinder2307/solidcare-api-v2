"""Static/unit tests for JWT and RBAC helpers — no database required."""

import uuid
from datetime import timedelta

import pytest

pytest.importorskip("jose")

from app.config import settings
from app.core.security.jwt import create_access_token, create_refresh_token, decode_token
from app.modules.auth.dependencies import CurrentUser


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(
        subject="doctor@clinic.com",
        user_id=user_id,
        org_id=org_id,
        clinic_ids=["clinic-a"],
        permissions=["patient:read", "encounter:create"],
        roles=["doctor"],
    )
    payload = decode_token(token)
    assert payload["sub"] == "doctor@clinic.com"
    assert payload["user_id"] == str(user_id)
    assert payload["org_id"] == str(org_id)
    assert payload["token_type"] == "access"
    assert "patient:read" in payload["permissions"]


def test_refresh_token_has_jti():
    user_id = uuid.uuid4()
    token, jti = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["token_type"] == "refresh"
    assert payload["jti"] == jti
    assert payload["sub"] == str(user_id)


def test_current_user_superadmin_bypass():
    user = CurrentUser(
        user_id=uuid.uuid4(),
        email="admin@solidcare.health",
        org_id=uuid.uuid4(),
        clinic_ids=[],
        permissions=[],
        roles=["superadmin"],
        is_superadmin=True,
    )
    assert user.can("audit:read")
    user.require("audit:read")  # should not raise


def test_current_user_denies_missing_permission():
    user = CurrentUser(
        user_id=uuid.uuid4(),
        email="reception@clinic.com",
        org_id=uuid.uuid4(),
        clinic_ids=[],
        permissions=["patient:read"],
        roles=["receptionist"],
    )
    assert not user.can("billing:create")
    with pytest.raises(Exception):
        user.require("billing:create")
