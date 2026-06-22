"""
Audit log middleware — records PHI access events to the audit_logs table.

The audit write is dispatched as a fire-and-forget background task so that it
never delays delivery of the HTTP response to the client.
"""

import asyncio
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.audit.writer import persist_request_audit

logger = logging.getLogger("audit")

PHI_PREFIXES = (
    "/api/v1/patients",
    "/api/v1/encounters",
    "/api/v1/prescriptions",
    "/api/v1/clinical",
)


async def _fire_audit(request: Request, status_code: int, elapsed_ms: float) -> None:
    """Background coroutine — errors are logged and swallowed so they never surface to callers."""
    try:
        await persist_request_audit(request, status_code=status_code, elapsed_ms=elapsed_ms)
    except Exception as exc:
        logger.error("audit background write failed: %s", exc)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        if self._is_phi_path(request.url.path):
            logger.info(
                "PHI_ACCESS path=%s method=%s status=%s elapsed_ms=%s",
                request.url.path,
                request.method,
                response.status_code,
                elapsed_ms,
            )
            # Schedule the DB write as a non-blocking background task so it does
            # not hold the HTTP response hostage while waiting for a DB connection.
            asyncio.create_task(
                _fire_audit(request, response.status_code, elapsed_ms),
                name="audit_write",
            )

        return response

    @staticmethod
    def _is_phi_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PHI_PREFIXES)
