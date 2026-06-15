"""
Audit log middleware — records PHI access events to the audit_logs table.
"""

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
            await persist_request_audit(
                request, status_code=response.status_code, elapsed_ms=elapsed_ms
            )

        return response

    @staticmethod
    def _is_phi_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PHI_PREFIXES)
