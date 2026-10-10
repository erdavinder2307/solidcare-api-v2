"""Wake the dev database when it was stopped for being idle (infra/db-autostop).

Only active when DB_WAKE_URL is set. A request that cannot reach the database then asks
the wake function to start the server and gets a 503 with Retry-After instead of a 500.
Wake calls back off (immediately, then 1, 2, 4, 5 min) while the database stays down, and
the backoff resets on the first successful connection.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions.errors import DatabaseStartingError

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 30
_BACKOFF_SECONDS = (60, 120, 240, 300)
_WAKE_TIMEOUT_SECONDS = 5.0

# asyncpg errors that mean "not up yet" rather than a bad query or bad credentials.
_STARTING_ERROR_NAMES = {"CannotConnectNowError", "ConnectionDoesNotExistError"}


class _WakeBackoff:
    def __init__(self) -> None:
        self.attempts = 0
        self.next_at = 0.0
        self.lock = asyncio.Lock()

    def due(self, now: float) -> bool:
        return now >= self.next_at

    def record(self, now: float) -> None:
        delay = _BACKOFF_SECONDS[min(self.attempts, len(_BACKOFF_SECONDS) - 1)]
        self.attempts += 1
        self.next_at = now + delay

    def reset(self) -> None:
        self.attempts = 0
        self.next_at = 0.0


_backoff = _WakeBackoff()


def is_database_unreachable(exc: BaseException) -> bool:
    """True when a connect attempt failed because the server is down or still starting."""
    if isinstance(exc, OSError):  # refused, timed out, DNS
        return True
    if isinstance(exc, DBAPIError):
        if exc.connection_invalidated:
            return True
        orig = exc.orig
        if isinstance(orig, OSError):
            return True
        return type(orig).__name__ in _STARTING_ERROR_NAMES
    return type(exc).__name__ in _STARTING_ERROR_NAMES


async def request_wake() -> None:
    """POST to the wake function, at most once per backoff step. Never raises."""
    async with _backoff.lock:
        now = time.monotonic()
        if not _backoff.due(now):
            return
        _backoff.record(now)
        try:
            async with httpx.AsyncClient(timeout=_WAKE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    settings.DB_WAKE_URL, headers={"x-functions-key": settings.DB_WAKE_KEY}
                )
            logger.warning(
                "Database unreachable; wake requested (HTTP %s, attempt %s)",
                response.status_code,
                _backoff.attempts,
            )
        except httpx.HTTPError as exc:
            logger.error("Database unreachable; wake request failed: %s", type(exc).__name__)


async def ensure_database_awake(session: AsyncSession) -> None:
    """Open the session's connection up front so an asleep database becomes a 503."""
    if not settings.DB_WAKE_URL:
        return
    try:
        await session.connection()
    except Exception as exc:
        if not is_database_unreachable(exc):
            raise
        await request_wake()
        raise DatabaseStartingError() from exc
    _backoff.reset()
