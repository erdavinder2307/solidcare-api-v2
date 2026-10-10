"""/health and /health/db with database auto-stop on (DB_WAKE_URL set). No database."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import ProgrammingError

import app.database as db_module
from app.core import db_wake
from app.main import app


@pytest.fixture(autouse=True)
def _wake_enabled():
    db_wake._backoff.reset()
    with (
        patch.object(db_wake.settings, "DB_WAKE_URL", "https://wake.example/api/wake"),
        patch.object(db_wake.settings, "DB_WAKE_KEY", "test-key"),
    ):
        yield
    db_wake._backoff.reset()


def _session_factory(side_effect=None):
    session = MagicMock()
    session.connection = AsyncMock(side_effect=side_effect)
    session.execute = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


async def _call(method: str, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path)


async def test_health_db_ready():
    factory, _ = _session_factory()
    with patch.object(db_module, "AsyncSessionLocal", factory):
        response = await _call("GET", "/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "ready"}


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_health_db_unreachable_wakes_and_reports_starting(method):
    factory, _ = _session_factory(ConnectionRefusedError())
    with (
        patch.object(db_module, "AsyncSessionLocal", factory),
        patch.object(db_wake, "request_wake", AsyncMock()) as wake,
    ):
        response = await _call(method, "/health/db")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"database": "starting", "error_code": "DB_STARTING"}
    wake.assert_awaited_once()


async def test_health_db_unreachable_without_wake_is_unavailable():
    factory, _ = _session_factory(ConnectionRefusedError())
    with (
        patch.object(db_wake.settings, "DB_WAKE_URL", ""),
        patch.object(db_module, "AsyncSessionLocal", factory),
        patch.object(db_wake, "request_wake", AsyncMock()) as wake,
    ):
        response = await _call("GET", "/health/db")

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    wake.assert_not_awaited()


async def test_health_db_other_errors_are_not_reported_as_starting():
    factory, _ = _session_factory(ProgrammingError("select", None, Exception("bad")))
    with (
        patch.object(db_module, "AsyncSessionLocal", factory),
        patch.object(db_wake, "request_wake", AsyncMock()) as wake,
    ):
        with pytest.raises(ProgrammingError):
            await db_wake.database_status()

    wake.assert_not_awaited()


async def test_health_does_not_touch_the_database_when_auto_stop_is_on():
    factory, session = _session_factory()
    with patch.object(db_module, "AsyncSessionLocal", factory):
        response = await _call("GET", "/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"].startswith("not checked")
    assert body["status"] == "healthy"
    factory.assert_not_called()
    session.execute.assert_not_awaited()
