"""
Audit log middleware — automatically records PHI access events for HIPAA/DPDP.
Full write auditing is handled at the service layer.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("audit")

PHI_PATHS = {
    "/api/v1/patients",
    "/api/v1/encounters",
    "/api/v1/prescriptions",
    "/api/v1/clinical",
}

READ_METHODS = {"GET"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        if self._is_phi_access(request) and response.status_code < 400:
            logger.info(
                "PHI_ACCESS path=%s method=%s status=%s elapsed_ms=%s user=%s org=%s ip=%s",
                request.url.path,
                request.method,
                response.status_code,
                elapsed_ms,
                request.state.__dict__.get("user_id", "anonymous"),
                request.state.__dict__.get("org_id", ""),
                request.client.host if request.client else "unknown",
            )

        return response

    @staticmethod
    def _is_phi_access(request: Request) -> bool:
        if request.method not in READ_METHODS:
            return False
        return any(request.url.path.startswith(p) for p in PHI_PATHS)
