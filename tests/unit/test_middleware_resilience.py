"""
Unit tests for middleware resilience against Redis unavailability.

These tests verify the critical production fixes:
1. RateLimitMiddleware degrades gracefully when Redis is down.
2. AuditMiddleware never blocks the HTTP response.
3. AuthService refresh token path survives Redis failures.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# RateLimitMiddleware — graceful degradation on Redis failure
# ---------------------------------------------------------------------------


class TestRateLimitMiddlewareResilience:
    """RateLimitMiddleware must never block a request due to Redis errors."""

    def _make_middleware(self):
        """Build a RateLimitMiddleware with REDIS_ENABLED=True but a broken Redis."""
        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as mock_settings:
            mock_settings.REDIS_ENABLED = False  # bypass __init__ connection
            mock_settings.ENV = "production"
            mw = RateLimitMiddleware(app)
        # Inject a broken redis mock directly
        broken_redis = AsyncMock()
        broken_redis.pipeline.return_value.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("Redis down"))
        mw._redis = broken_redis
        return mw

    @pytest.mark.asyncio
    async def test_bypass_when_redis_disabled(self):
        """Pass-through when REDIS_ENABLED is False."""
        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            mw = RateLimitMiddleware(app)
        mw._redis = None

        request = MagicMock()
        request.client.host = "1.2.3.4"
        request.url.path = "/api/v1/patients"

        sentinel = object()
        call_next = AsyncMock(return_value=sentinel)

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            result = await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_bypass_when_redis_none(self):
        """Pass-through when _redis is None (REDIS_ENABLED was False at startup)."""
        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            mw = RateLimitMiddleware(app)

        # Force None — simulates a startup where REDIS_ENABLED was False
        mw._redis = None

        request = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = True  # even if setting changed, _redis is None
            s.ENV = "production"
            await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_redis_connection_error(self):
        """When Redis raises, the request must still be processed (not raise)."""
        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            mw = RateLimitMiddleware(app)

        # Inject a broken pipeline
        broken_pipeline = MagicMock()
        broken_pipeline.zremrangebyscore = MagicMock()
        broken_pipeline.zadd = MagicMock()
        broken_pipeline.zcard = MagicMock()
        broken_pipeline.expire = MagicMock()
        broken_pipeline.execute = AsyncMock(side_effect=ConnectionRefusedError("Redis refused"))

        broken_redis = MagicMock()
        broken_redis.pipeline.return_value = broken_pipeline
        mw._redis = broken_redis

        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.url.path = "/api/v1/appointments"

        sentinel = object()
        call_next = AsyncMock(return_value=sentinel)

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = True
            s.ENV = "production"
            s.RATE_LIMIT_PER_MINUTE = 60
            s.RATE_LIMIT_AUTH_PER_MINUTE = 10
            result = await mw.dispatch(request, call_next)

        # Must have passed through despite Redis failure
        call_next.assert_awaited_once()
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_redis_timeout(self):
        """TimeoutError from redis-py must degrade gracefully."""
        import asyncio

        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            mw = RateLimitMiddleware(app)

        broken_pipeline = MagicMock()
        broken_pipeline.execute = AsyncMock(side_effect=asyncio.TimeoutError())
        broken_redis = MagicMock()
        broken_redis.pipeline.return_value = broken_pipeline
        mw._redis = broken_redis

        request = MagicMock()
        request.client.host = "10.0.0.2"
        request.url.path = "/api/v1/doctors"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = True
            s.ENV = "production"
            s.RATE_LIMIT_PER_MINUTE = 60
            s.RATE_LIMIT_AUTH_PER_MINUTE = 10
            await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_limit_enforced_when_redis_works(self):
        """When Redis is working, requests over the limit get 429."""
        from starlette.responses import JSONResponse

        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "production"
            mw = RateLimitMiddleware(app)

        # Pipeline returns count (index 2) > limit; methods on the pipeline are no-ops
        working_pipeline = MagicMock()
        working_pipeline.zremrangebyscore = MagicMock()
        working_pipeline.zadd = MagicMock()
        working_pipeline.zcard = MagicMock()
        working_pipeline.expire = MagicMock()
        working_pipeline.execute = AsyncMock(return_value=[0, 1, 61, True])

        working_redis = MagicMock()
        working_redis.pipeline = MagicMock(return_value=working_pipeline)
        mw._redis = working_redis

        request = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/v1/appointments"

        call_next = AsyncMock(return_value=MagicMock())

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = True
            s.ENV = "production"
            s.RATE_LIMIT_PER_MINUTE = 60
            s.RATE_LIMIT_AUTH_PER_MINUTE = 10
            result = await mw.dispatch(request, call_next)

        call_next.assert_not_awaited()
        assert isinstance(result, JSONResponse)
        assert result.status_code == 429

    @pytest.mark.asyncio
    async def test_env_test_always_bypasses(self):
        """In test ENV, rate limiting is completely skipped."""
        from app.core.middleware.rate_limit import RateLimitMiddleware

        app = MagicMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.ENV = "test"
            mw = RateLimitMiddleware(app)

        call_next = AsyncMock(return_value=MagicMock())
        request = MagicMock()

        with patch("app.core.middleware.rate_limit.settings") as s:
            s.REDIS_ENABLED = True
            s.ENV = "test"
            await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()


# ---------------------------------------------------------------------------
# AuditMiddleware — fire-and-forget must not delay response
# ---------------------------------------------------------------------------


class TestAuditMiddlewareNonBlocking:
    """AuditMiddleware must return the response immediately without awaiting the DB write."""

    @pytest.mark.asyncio
    async def test_phi_path_response_not_delayed(self):
        """Response is returned before the audit task runs."""
        import app.core.middleware.audit as audit_module
        from app.core.middleware.audit import AuditMiddleware

        app = MagicMock()
        mw = AuditMiddleware(app)

        audit_complete = asyncio.Event()
        original = audit_module.persist_request_audit

        async def instant_audit(*args, **kwargs):
            audit_complete.set()
            audit_module.persist_request_audit = original  # self-restore

        audit_module.persist_request_audit = instant_audit

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        request = MagicMock()
        request.url.path = "/api/v1/patients"
        request.method = "GET"

        result = await mw.dispatch(request, call_next)

        # Response returned immediately — audit task not yet scheduled/run
        assert result is mock_response
        assert not audit_complete.is_set()

        # Yield to let the scheduled background task run
        await asyncio.sleep(0)
        assert audit_complete.is_set()

    @pytest.mark.asyncio
    async def test_non_phi_path_no_audit(self):
        """Non-PHI paths must not trigger any audit writes."""
        import app.core.middleware.audit as audit_module
        from app.core.middleware.audit import AuditMiddleware

        app = MagicMock()
        mw = AuditMiddleware(app)

        called = False

        async def spy_audit(*args, **kwargs):
            nonlocal called
            called = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        original = audit_module.persist_request_audit
        audit_module.persist_request_audit = spy_audit
        try:
            request = MagicMock()
            request.url.path = "/api/v1/doctors"
            request.method = "GET"

            await mw.dispatch(request, call_next)
            await asyncio.sleep(0.05)
        finally:
            audit_module.persist_request_audit = original

        assert not called

    @pytest.mark.asyncio
    async def test_audit_db_failure_does_not_raise(self):
        """A DB error in the background task must never propagate to the caller."""
        import app.core.middleware.audit as audit_module
        from app.core.middleware.audit import AuditMiddleware

        app = MagicMock()
        mw = AuditMiddleware(app)

        async def failing_audit(*args, **kwargs):
            raise RuntimeError("DB pool exhausted")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        original = audit_module.persist_request_audit
        audit_module.persist_request_audit = failing_audit
        try:
            request = MagicMock()
            request.url.path = "/api/v1/patients"
            request.method = "POST"

            result = await mw.dispatch(request, call_next)
            # Allow the background task to complete (and fail silently)
            await asyncio.sleep(0.05)
        finally:
            audit_module.persist_request_audit = original

        assert result is mock_response


# ---------------------------------------------------------------------------
# AuthService — Redis timeout on refresh token revocation check
# ---------------------------------------------------------------------------


class TestAuthServiceRedisResilience:
    """AuthService._issue_tokens and refresh_token must survive Redis failures."""

    def _make_service(self):
        """Build an AuthService with Redis patched out."""
        from app.modules.auth.service import AuthService

        repo = AsyncMock()
        with patch("app.config.settings") as s:
            s.REDIS_ENABLED = False
            s.JWT_SECRET_KEY = "test-secret"
            s.JWT_ALGORITHM = "HS256"
            s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
            s.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
            svc = AuthService(repo)
        return svc, repo

    @pytest.mark.asyncio
    async def test_refresh_proceeds_when_redis_down(self):
        """refresh_token must succeed even when Redis raises ConnectionRefusedError."""
        from app.core.exceptions.errors import UnauthorizedError
        from app.core.security.jwt import create_refresh_token

        svc, repo = self._make_service()

        # Inject broken redis
        broken_redis = AsyncMock()
        broken_redis.get = AsyncMock(side_effect=ConnectionRefusedError("Redis refused"))
        svc._redis = broken_redis

        user_id = uuid.uuid4()
        refresh_tok, jti = create_refresh_token(user_id)

        # Mock user returned from DB
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "test@clinic.com"
        from app.modules.users.models import UserStatus

        mock_user.status = UserStatus.ACTIVE
        mock_user.mfa_enabled = False
        mock_user.organization_id = uuid.uuid4()
        mock_user.user_roles = []
        repo.get_user_by_id = AsyncMock(return_value=mock_user)
        repo.update_last_login = AsyncMock()

        with patch("app.modules.auth.service.create_access_token") as mock_at, \
             patch("app.modules.auth.service.create_refresh_token") as mock_rt, \
             patch("app.config.settings") as s:
            s.REDIS_ENABLED = True
            s.JWT_SECRET_KEY = "test-secret"
            s.JWT_ALGORITHM = "HS256"
            s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
            s.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
            mock_at.return_value = "new-access-token"
            mock_rt.return_value = ("new-refresh-token", str(uuid.uuid4()))

            from app.modules.auth.schemas import TokenResponse
            from unittest.mock import patch as patch2
            with patch2.object(svc, "_issue_tokens", new_callable=AsyncMock) as mock_issue:
                mock_issue.return_value = TokenResponse(
                    access_token="new-access",
                    refresh_token="new-refresh",
                    expires_in=900,
                    requires_mfa=False,
                )
                result = await svc.refresh_token(refresh_tok)

        assert result.access_token == "new-access"

    @pytest.mark.asyncio
    async def test_revoked_token_still_rejected_when_redis_works(self):
        """A revoked JTI in Redis must still result in UnauthorizedError."""
        from app.core.exceptions.errors import UnauthorizedError
        from app.core.security.jwt import create_refresh_token

        svc, repo = self._make_service()

        working_redis = AsyncMock()
        working_redis.get = AsyncMock(return_value="1")  # revoked
        svc._redis = working_redis

        user_id = uuid.uuid4()
        refresh_tok, jti = create_refresh_token(user_id)

        with pytest.raises(UnauthorizedError, match="revoked"):
            await svc.refresh_token(refresh_tok)

    @pytest.mark.asyncio
    async def test_logout_redis_failure_does_not_raise(self):
        """logout() must always succeed even when Redis is down."""
        from app.core.security.jwt import create_refresh_token

        svc, repo = self._make_service()

        broken_redis = AsyncMock()
        broken_redis.setex = AsyncMock(side_effect=ConnectionRefusedError("Redis down"))
        svc._redis = broken_redis

        user_id = uuid.uuid4()
        refresh_tok, _ = create_refresh_token(user_id)

        # Should not raise
        await svc.logout(refresh_tok)
