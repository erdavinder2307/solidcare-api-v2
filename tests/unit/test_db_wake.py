"""Wake-and-retry path for the idle-stopped dev database (app/core/db_wake.py). No database."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core import db_wake
from app.core.exceptions.errors import DatabaseStartingError
from app.core.exceptions.handlers import database_starting_handler


class CannotConnectNowError(Exception):
    """Stands in for asyncpg's 'the database system is starting up' error."""


@pytest.fixture(autouse=True)
def _wake_enabled():
    db_wake._backoff.reset()
    with patch.object(db_wake.settings, "DB_WAKE_URL", "https://wake.example/api/wake"), \
         patch.object(db_wake.settings, "DB_WAKE_KEY", "test-key"):
        yield
    db_wake._backoff.reset()


@pytest.fixture
def wake_client():
    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=202))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(db_wake.httpx, "AsyncClient", factory):
        yield client


def _session(side_effect=None):
    session = MagicMock()
    session.connection = AsyncMock(side_effect=side_effect)
    return session


async def test_refused_connection_wakes_once_and_raises_503(wake_client):
    with pytest.raises(DatabaseStartingError):
        await db_wake.ensure_database_awake(_session(ConnectionRefusedError()))

    wake_client.post.assert_awaited_once_with(
        "https://wake.example/api/wake", headers={"x-functions-key": "test-key"}
    )


async def test_wake_backs_off_while_database_stays_down(wake_client):
    for _ in range(3):
        with pytest.raises(DatabaseStartingError):
            await db_wake.ensure_database_awake(_session(TimeoutError()))

    assert wake_client.post.await_count == 1


async def test_wake_again_after_backoff_step(wake_client):
    with pytest.raises(DatabaseStartingError):
        await db_wake.ensure_database_awake(_session(TimeoutError()))
    db_wake._backoff.next_at = 0.0  # the 60 s step has passed

    with pytest.raises(DatabaseStartingError):
        await db_wake.ensure_database_awake(_session(TimeoutError()))

    assert wake_client.post.await_count == 2
    assert db_wake._backoff.attempts == 2


async def test_successful_connection_resets_backoff(wake_client):
    with pytest.raises(DatabaseStartingError):
        await db_wake.ensure_database_awake(_session(OSError()))

    await db_wake.ensure_database_awake(_session())

    assert db_wake._backoff.attempts == 0
    assert db_wake._backoff.due(0.0)


async def test_database_starting_up_counts_as_unreachable(wake_client):
    exc = DBAPIError("connect", None, CannotConnectNowError("the database system is starting up"))
    with pytest.raises(DatabaseStartingError):
        await db_wake.ensure_database_awake(_session(exc))

    wake_client.post.assert_awaited_once()


async def test_other_database_errors_are_not_turned_into_503(wake_client):
    exc = ProgrammingError("select", None, Exception("syntax error"))
    with pytest.raises(ProgrammingError):
        await db_wake.ensure_database_awake(_session(exc))

    wake_client.post.assert_not_awaited()


async def test_wake_failure_still_returns_503():
    import httpx

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("down"))
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(db_wake.httpx, "AsyncClient", factory):
        with pytest.raises(DatabaseStartingError):
            await db_wake.ensure_database_awake(_session(ConnectionRefusedError()))


async def test_disabled_without_wake_url_keeps_original_error(wake_client):
    with patch.object(db_wake.settings, "DB_WAKE_URL", ""):
        session = _session(ConnectionRefusedError())
        await db_wake.ensure_database_awake(session)

    session.connection.assert_not_awaited()
    wake_client.post.assert_not_awaited()


async def test_handler_returns_friendly_503_with_retry_after():
    app = FastAPI()
    app.add_exception_handler(DatabaseStartingError, database_starting_handler)

    @app.get("/x")
    async def _x():
        raise DatabaseStartingError()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/x")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    body = response.json()
    assert body["error_code"] == "DATABASE_STARTING"
    assert "try again" in body["detail"]
