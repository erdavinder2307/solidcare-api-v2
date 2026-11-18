"""
Demo tenant mode (SE-4193).

An organization with `is_demo = TRUE` is a showcase tenant: the API blocks
destructive operations for it (see core/middleware/demo_guard.py) and suppresses
every outbound message — SMS, WhatsApp, email — sent on its behalf (see
shared/services/notification_delivery.py). Both checks key off the organization,
so they also hold for background jobs, not only for HTTP requests.
"""

import asyncio
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db_context

logger = logging.getLogger(__name__)

DEMO_BLOCKED_DETAIL = "Not allowed in the demo clinic"


def _as_uuid(org_id: uuid.UUID | str) -> uuid.UUID:
    return org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))


# Plain SQL rather than the ORM model so the check also works in Celery workers,
# where the full mapper registry (app/register_models.py) may not be loaded.
_IS_DEMO_SQL = text("SELECT is_demo FROM organizations WHERE id = :org_id")


async def _lookup(conn: AsyncSession | AsyncConnection, org_id: uuid.UUID) -> bool:
    result = await conn.execute(_IS_DEMO_SQL, {"org_id": org_id})
    return bool(result.scalar_one_or_none())


async def is_demo_org(org_id: uuid.UUID | str) -> bool:
    """True when the organization is the demo tenant. Async callers (requests, event handlers)."""
    async with get_db_context() as session:
        return await _lookup(session, _as_uuid(org_id))


def is_demo_org_sync(org_id: uuid.UUID | str) -> bool:
    """Sync variant for Celery workers / provider code that runs outside an event loop.

    Uses a throwaway NullPool engine so no pooled asyncpg connection is shared
    across the separate event loops that `asyncio.run` creates per call.
    """

    async def _run() -> bool:
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                return await _lookup(conn, _as_uuid(org_id))
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def outbound_messages_allowed(org_id: uuid.UUID | str | None, channel: str) -> bool:
    """Single gate for every outbound message (SMS, WhatsApp, email).

    Fails closed: a message is sent only when we can prove the organization is
    NOT a demo tenant. An unknown org or a failed lookup suppresses the send.
    """
    if org_id is None:
        logger.warning("Outbound %s suppressed: no organization given", channel)
        return False
    try:
        demo = is_demo_org_sync(org_id)
    except Exception:
        logger.exception("Outbound %s suppressed: demo-tenant lookup failed for org %s", channel, org_id)
        return False
    if demo:
        logger.info("Outbound %s suppressed for demo organization %s", channel, org_id)
        return False
    return True
