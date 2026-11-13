"""
Demo-tenant guard middleware (SE-4193).

When the request's active organization is the demo tenant, destructive
operations are rejected with 403 before they reach a route: every HTTP DELETE,
plus the few POSTs listed in BLOCKED_ACTIONS that would lock other demo viewers
out of the shared demo accounts. Reads and normal create/update keep working so
the demo stays usable.
"""

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.demo import DEMO_BLOCKED_DETAIL, is_demo_org
from app.core.exceptions.handlers import _problem_detail

BLOCKED_METHODS = {"DELETE"}
BLOCKED_ACTIONS = {
    ("POST", "/api/v1/auth/change-password"),
    ("POST", "/api/v1/auth/mfa/setup"),
    ("POST", "/api/v1/auth/mfa/confirm"),
}


def _active_org_id(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:], settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except PyJWTError:
        return None  # unauthenticated: the route's own auth dependency rejects it
    # Same precedence as get_current_user: the ACTIVE org (F2), then the home org.
    return payload.get("active_org_id") or payload.get("org_id")


def is_destructive(method: str, path: str) -> bool:
    method = method.upper()
    return method in BLOCKED_METHODS or (method, path.rstrip("/")) in BLOCKED_ACTIONS


class DemoGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if is_destructive(request.method, request.url.path):
            org_id = _active_org_id(request)
            try:
                demo = bool(org_id) and await is_demo_org(org_id)
            except ValueError:
                demo = False  # malformed org id: the route's auth dependency rejects it
            if demo:
                return JSONResponse(
                    status_code=403,
                    content=_problem_detail(403, "DEMO_READ_ONLY", DEMO_BLOCKED_DETAIL, request),
                )
        return await call_next(request)
