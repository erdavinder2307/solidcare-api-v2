"""
SE-4061: CORS headers must be present on responses produced by the other middlewares.

Starlette makes the last-added middleware the outermost one. If CORSMiddleware is not
outermost, a response short-circuited by an inner middleware (e.g. a 429 from
RateLimitMiddleware) goes out without Access-Control-Allow-Origin, and the browser
reports a CORS failure instead of the real status.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

ORIGIN = "https://solidcare.org"
LOGIN_PATH = "/api/v1/auth/login"


def _make_app():
    from app.config import settings
    from app.main import create_app

    with patch.object(settings, "CORS_ORIGINS", ["https://solidcare.org", "https://www.solidcare.org"]):
        return create_app()


@pytest.mark.asyncio
async def test_preflight_to_login_allows_solidcare_origin():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.options(
            LOGIN_PATH,
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


@pytest.mark.asyncio
async def test_rate_limit_response_carries_cors_header():
    from app.core.middleware.rate_limit import RateLimitMiddleware

    async def always_429(self, request, call_next):
        return JSONResponse(status_code=429, content={"detail": "Too many requests. Please slow down."})

    app = _make_app()
    with patch.object(RateLimitMiddleware, "dispatch", always_429):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(LOGIN_PATH, json={}, headers={"Origin": ORIGIN})

    assert resp.status_code == 429
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


def _make_app_with_failing_route():
    app = _make_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("simulated database outage")

    return app


@pytest.mark.asyncio
async def test_unhandled_exception_500_carries_cors_header():
    # The Exception handler runs in ServerErrorMiddleware, outside all add_middleware() entries.
    app = _make_app_with_failing_route()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/boom", headers={"Origin": ORIGIN})

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "INTERNAL_ERROR"
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


@pytest.mark.asyncio
async def test_unhandled_exception_500_has_no_cors_header_for_other_origin():
    app = _make_app_with_failing_route()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/boom", headers={"Origin": "https://evil.example"})

    assert resp.status_code == 500
    assert "access-control-allow-origin" not in resp.headers
