"""
Unit tests for demo-tenant mode (SE-4193, D3).

1. DemoGuardMiddleware blocks destructive operations (DELETE + listed POSTs) with
   403 when the active org is a demo tenant, and lets everything else through.
2. Every outbound channel (email, SMS) is suppressed for a demo org — including
   when sent from a background (Celery) task — and still sent for a real org.
3. The appointment-booked handler carries the org id to the outbound tasks.

No database: the demo-tenant lookup is patched.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.middleware.demo_guard import DemoGuardMiddleware

DEMO_ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
REAL_ORG = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _token(org_id: uuid.UUID, active_org_id: uuid.UUID | None = None) -> str:
    payload = {"sub": "demo.user@example.test", "user_id": str(uuid.uuid4()), "org_id": str(org_id)}
    if active_org_id:
        payload["active_org_id"] = str(active_org_id)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def _fake_is_demo(org_id) -> bool:
    return uuid.UUID(str(org_id)) == DEMO_ORG


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(DemoGuardMiddleware)

    @app.get("/api/v1/patients")
    async def list_patients():
        return {"ok": True}

    @app.post("/api/v1/patients")
    async def create_patient():
        return {"ok": True}

    @app.patch("/api/v1/patients/{pid}")
    async def update_patient(pid: str):
        return {"ok": True}

    @app.delete("/api/v1/patients/{pid}", status_code=204)
    async def delete_patient(pid: str):
        return None

    @app.post("/api/v1/auth/change-password")
    async def change_password():
        return {"ok": True}

    return app


async def _request(method: str, path: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with patch("app.core.middleware.demo_guard.is_demo_org", side_effect=_fake_is_demo):
        async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
            return await client.request(method, path, headers=headers)


# ---------------------------------------------------------------------------
# Destructive-operation guard
# ---------------------------------------------------------------------------


class TestDemoGuardMiddleware:
    @pytest.mark.asyncio
    async def test_delete_blocked_for_demo_org(self):
        resp = await _request("DELETE", f"/api/v1/patients/{uuid.uuid4()}", _token(DEMO_ORG))
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"] == "Not allowed in the demo clinic"
        assert body["error_code"] == "DEMO_READ_ONLY"

    @pytest.mark.asyncio
    async def test_delete_blocked_when_active_org_is_demo(self):
        # Home org is real, but the user switched to the demo org (F2 active_org_id).
        resp = await _request("DELETE", f"/api/v1/patients/{uuid.uuid4()}", _token(REAL_ORG, DEMO_ORG))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_allowed_for_real_org(self):
        resp = await _request("DELETE", f"/api/v1/patients/{uuid.uuid4()}", _token(REAL_ORG))
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_allowed_when_active_org_is_real(self):
        resp = await _request("DELETE", f"/api/v1/patients/{uuid.uuid4()}", _token(DEMO_ORG, REAL_ORG))
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_listed_destructive_post_blocked_for_demo_org(self):
        resp = await _request("POST", "/api/v1/auth/change-password", _token(DEMO_ORG))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/v1/patients"),
            ("POST", "/api/v1/patients"),
            ("PATCH", "/api/v1/patients/abc"),
        ],
    )
    async def test_reads_and_normal_writes_allowed_for_demo_org(self, method, path):
        resp = await _request(method, path, _token(DEMO_ORG))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_delete_passes_through_to_route_auth(self):
        # No token: the guard does not decide; the route's own auth dependency does.
        resp = await _request("DELETE", f"/api/v1/patients/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_non_destructive_requests_skip_the_db_lookup(self):
        lookup = AsyncMock(return_value=True)
        with patch("app.core.middleware.demo_guard.is_demo_org", lookup):
            async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/patients", headers={"Authorization": f"Bearer {_token(DEMO_ORG)}"}
                )
        assert resp.status_code == 200
        lookup.assert_not_awaited()


# ---------------------------------------------------------------------------
# Outbound-message gate
# ---------------------------------------------------------------------------


def _fake_is_demo_sync(org_id) -> bool:
    return uuid.UUID(str(org_id)) == DEMO_ORG


@pytest.fixture
def providers():
    """Configured providers with the network calls mocked out."""
    ok = MagicMock(status_code=202)
    with (
        patch("app.shared.services.notification_delivery.settings") as s,
        patch("app.shared.services.notification_delivery.SendGridAPIClient") as sendgrid,
        patch("app.shared.services.notification_delivery.httpx.post", return_value=ok) as http_post,
        patch("app.core.demo.is_demo_org_sync", side_effect=_fake_is_demo_sync),
    ):
        s.SENDGRID_API_KEY = "test-sendgrid-key"
        s.MSG91_AUTH_KEY = "test-msg91-key"
        s.MSG91_SENDER_ID = "TEST"
        s.EMAIL_FROM_ADDRESS = "noreply@example.test"
        s.EMAIL_FROM_NAME = "Test"
        sendgrid.return_value.send.return_value = ok
        yield {"email": sendgrid.return_value.send, "sms": http_post}


class TestOutboundGate:
    def test_email_not_sent_for_demo_org(self, providers):
        from app.shared.services.notification_delivery import send_email_via_sendgrid

        assert send_email_via_sendgrid("p@example.test", "S", "B", org_id=str(DEMO_ORG)) is False
        providers["email"].assert_not_called()

    def test_email_sent_for_real_org(self, providers):
        from app.shared.services.notification_delivery import send_email_via_sendgrid

        assert send_email_via_sendgrid("p@example.test", "S", "B", org_id=str(REAL_ORG)) is True
        providers["email"].assert_called_once()

    def test_sms_not_sent_for_demo_org(self, providers):
        from app.shared.services.notification_delivery import send_sms_via_msg91

        assert send_sms_via_msg91("9000000000", "hi", org_id=str(DEMO_ORG)) is False
        providers["sms"].assert_not_called()

    def test_sms_sent_for_real_org(self, providers):
        from app.shared.services.notification_delivery import send_sms_via_msg91

        assert send_sms_via_msg91("9000000000", "hi", org_id=str(REAL_ORG)) is True
        providers["sms"].assert_called_once()

    def test_unknown_org_fails_closed(self, providers):
        from app.shared.services.notification_delivery import (
            send_email_via_sendgrid,
            send_sms_via_msg91,
        )

        assert send_email_via_sendgrid("p@example.test", "S", "B", org_id=None) is False
        assert send_sms_via_msg91("9000000000", "hi", org_id=None) is False
        providers["email"].assert_not_called()
        providers["sms"].assert_not_called()

    def test_lookup_failure_fails_closed(self, providers):
        from app.shared.services.notification_delivery import send_sms_via_msg91

        with patch("app.core.demo.is_demo_org_sync", side_effect=ConnectionError("db down")):
            assert send_sms_via_msg91("9000000000", "hi", org_id=str(REAL_ORG)) is False
        providers["sms"].assert_not_called()

    def test_background_tasks_suppress_for_demo_org(self, providers):
        """Celery tasks (no HTTP request) are covered too: the gate keys off the org."""
        from app.core.background.tasks.notification_tasks import (
            send_email_notification,
            send_sms_notification,
        )

        assert send_sms_notification.run("9000000000", "t", {"message": "hi"}, org_id=str(DEMO_ORG)) is False
        assert send_email_notification.run("p@example.test", "t", {}, org_id=str(DEMO_ORG)) is False
        providers["sms"].assert_not_called()
        providers["email"].assert_not_called()

    def test_background_tasks_send_for_real_org(self, providers):
        from app.core.background.tasks.notification_tasks import (
            send_email_notification,
            send_sms_notification,
        )

        assert send_sms_notification.run("9000000000", "t", {"message": "hi"}, org_id=str(REAL_ORG)) is True
        assert send_email_notification.run("p@example.test", "t", {}, org_id=str(REAL_ORG)) is True
        providers["sms"].assert_called_once()
        providers["email"].assert_called_once()


# ---------------------------------------------------------------------------
# Event handler passes the org through
# ---------------------------------------------------------------------------


class TestAppointmentBookedHandler:
    @pytest.mark.asyncio
    async def test_org_id_is_passed_to_outbound_tasks(self):
        from app.core.events.handlers import notification_handler as h

        event = h.AppointmentBooked(
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            clinic_id=uuid.uuid4(),
            appointment_date="2026-01-01",
            appointment_time="10:00",
            patient_phone="9000000000",
            patient_email="p@example.test",
            org_id=DEMO_ORG,
        )
        with (
            patch.object(h, "create_in_app_notification", AsyncMock()),
            patch.object(h.send_sms_notification, "delay") as sms_delay,
            patch.object(h.send_email_notification, "delay") as email_delay,
        ):
            await h.on_appointment_booked(event)

        assert sms_delay.call_args.kwargs["org_id"] == str(DEMO_ORG)
        assert email_delay.call_args.kwargs["org_id"] == str(DEMO_ORG)


def test_guard_is_registered_on_the_real_app():
    from app.main import app

    assert DemoGuardMiddleware in [m.cls for m in app.user_middleware]


# ---------------------------------------------------------------------------
# Password reset is refused for the demo clinic's shared logins
# ---------------------------------------------------------------------------


def _auth_service(demo_orgs: set[uuid.UUID], user=None):
    from app.modules.auth.service import AuthService

    repo = MagicMock()
    repo.is_demo_org = AsyncMock(side_effect=lambda org_id: org_id in demo_orgs)
    repo.get_user_by_email = AsyncMock(return_value=user)
    repo.get_user_by_id = AsyncMock(return_value=user)
    service = AuthService(repo)
    service._redis = MagicMock()
    service._redis.setex = AsyncMock()
    service._redis.delete = AsyncMock()
    service._redis.get = AsyncMock(return_value=str(user.id) if user else None)
    return service, repo


def _user_in(org_id: uuid.UUID):
    return MagicMock(id=uuid.uuid4(), organization_id=org_id, hashed_password="old-hash")


class TestDemoPasswordReset:
    async def test_request_refused_for_demo_org_before_user_lookup(self):
        from app.core.exceptions.errors import DemoReadOnlyError

        service, repo = _auth_service({DEMO_ORG}, _user_in(DEMO_ORG))
        with pytest.raises(DemoReadOnlyError, match="demo clinic"):
            await service.request_password_reset("admin@demo.example.com", DEMO_ORG)
        repo.get_user_by_email.assert_not_awaited()  # no user enumeration
        service._redis.setex.assert_not_awaited()

    async def test_request_allowed_for_real_org(self):
        service, _ = _auth_service({DEMO_ORG}, _user_in(REAL_ORG))
        token = await service.request_password_reset("someone@example.test", REAL_ORG)
        assert token
        service._redis.setex.assert_awaited_once()

    async def test_confirm_refused_for_demo_org_user(self):
        from app.core.exceptions.errors import DemoReadOnlyError

        user = _user_in(DEMO_ORG)
        service, _ = _auth_service({DEMO_ORG}, user)
        with pytest.raises(DemoReadOnlyError):
            await service.confirm_password_reset("tok", "new-password-123")
        assert user.hashed_password == "old-hash"
        service._redis.delete.assert_awaited_once_with("pwd_reset:tok")  # token burned

    async def test_confirm_allowed_for_real_org_user(self):
        user = _user_in(REAL_ORG)
        service, _ = _auth_service({DEMO_ORG}, user)
        await service.confirm_password_reset("tok", "new-password-123")
        assert user.hashed_password != "old-hash"

    async def test_endpoint_returns_403_demo_read_only(self):
        from app.core.exceptions.errors import SolidcareException
        from app.core.exceptions.handlers import solidcare_exception_handler
        from app.modules.auth.router import get_auth_service, router

        service, _ = _auth_service({DEMO_ORG}, _user_in(DEMO_ORG))
        app = FastAPI()
        app.add_exception_handler(SolidcareException, solidcare_exception_handler)
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_auth_service] = lambda: service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/password-reset",
                                     json={"email": "admin@demo.example.com"},
                                     headers={"X-Org-Id": str(DEMO_ORG)})
        assert resp.status_code == 403
        body = resp.json()
        assert body["error_code"] == "DEMO_READ_ONLY"
        assert "reset_token" not in body
