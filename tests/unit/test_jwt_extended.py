"""Unit tests for JWT security edge cases — no database required."""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("jose")

from jose import jwt

from app.core.exceptions.errors import UnauthorizedError
from app.core.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_access_token(**overrides):
    defaults = dict(
        subject="doctor@clinic.com",
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        clinic_ids=["clinic-1"],
        permissions=["patient:read"],
        roles=["doctor"],
    )
    defaults.update(overrides)
    return create_access_token(**defaults)


# ---------------------------------------------------------------------------
# Access token field coverage
# ---------------------------------------------------------------------------

class TestAccessTokenFields:
    def test_contains_subject(self):
        token = _make_access_token(subject="nurse@hospital.in")
        payload = decode_token(token)
        assert payload["sub"] == "nurse@hospital.in"

    def test_contains_user_id(self):
        uid = uuid.uuid4()
        token = _make_access_token(user_id=uid)
        payload = decode_token(token)
        assert payload["user_id"] == str(uid)

    def test_contains_org_id(self):
        oid = uuid.uuid4()
        token = _make_access_token(org_id=oid)
        payload = decode_token(token)
        assert payload["org_id"] == str(oid)

    def test_contains_clinic_ids(self):
        token = _make_access_token(clinic_ids=["clinic-a", "clinic-b"])
        payload = decode_token(token)
        assert payload["clinic_ids"] == ["clinic-a", "clinic-b"]

    def test_contains_permissions(self):
        token = _make_access_token(permissions=["encounter:create", "billing:read"])
        payload = decode_token(token)
        assert "encounter:create" in payload["permissions"]
        assert "billing:read" in payload["permissions"]

    def test_contains_roles(self):
        token = _make_access_token(roles=["doctor", "org_admin"])
        payload = decode_token(token)
        assert "doctor" in payload["roles"]

    def test_token_type_is_access(self):
        token = _make_access_token()
        payload = decode_token(token)
        assert payload["token_type"] == "access"

    def test_superadmin_flag_false_by_default(self):
        token = _make_access_token()
        payload = decode_token(token)
        assert payload["is_superadmin"] is False

    def test_superadmin_flag_can_be_set(self):
        token = _make_access_token(is_superadmin=True)
        payload = decode_token(token)
        assert payload["is_superadmin"] is True

    def test_has_jti(self):
        token = _make_access_token()
        payload = decode_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_has_exp(self):
        token = _make_access_token()
        payload = decode_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()

    def test_two_tokens_have_different_jtis(self):
        t1 = _make_access_token()
        t2 = _make_access_token()
        assert decode_token(t1)["jti"] != decode_token(t2)["jti"]


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

class TestRefreshToken:
    def test_token_type_is_refresh(self):
        token, _ = create_refresh_token(uuid.uuid4())
        payload = decode_token(token)
        assert payload["token_type"] == "refresh"

    def test_returned_jti_matches_payload(self):
        token, jti = create_refresh_token(uuid.uuid4())
        payload = decode_token(token)
        assert payload["jti"] == jti

    def test_sub_is_user_id(self):
        uid = uuid.uuid4()
        token, _ = create_refresh_token(uid)
        payload = decode_token(token)
        assert payload["sub"] == str(uid)

    def test_two_refresh_tokens_have_different_jtis(self):
        uid = uuid.uuid4()
        _, jti1 = create_refresh_token(uid)
        _, jti2 = create_refresh_token(uid)
        assert jti1 != jti2


# ---------------------------------------------------------------------------
# decode_token error cases
# ---------------------------------------------------------------------------

class TestDecodeTokenErrors:
    def test_garbage_token_raises_unauthorized(self):
        with pytest.raises(UnauthorizedError):
            decode_token("not.a.real.token")

    def test_empty_string_raises_unauthorized(self):
        with pytest.raises(UnauthorizedError):
            decode_token("")

    def test_tampered_signature_raises_unauthorized(self):
        token = _make_access_token()
        # Flip the last character of the token to corrupt the signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(UnauthorizedError):
            decode_token(tampered)

    def test_expired_token_raises_unauthorized(self):
        from app.config import settings

        uid = uuid.uuid4()
        past = datetime.now(UTC) - timedelta(hours=1)
        payload = {
            "sub": "user@test.com",
            "user_id": str(uid),
            "org_id": str(uuid.uuid4()),
            "clinic_ids": [],
            "permissions": [],
            "roles": [],
            "is_superadmin": False,
            "exp": past,
            "iat": past - timedelta(minutes=30),
            "jti": str(uuid.uuid4()),
            "token_type": "access",
        }
        expired_token = jwt.encode(
            payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        with pytest.raises(UnauthorizedError):
            decode_token(expired_token)
