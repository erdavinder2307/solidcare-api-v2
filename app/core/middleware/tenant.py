"""
Tenant context middleware.

Extracts the org_id from the JWT and stores it in a context variable
so that all repository queries are automatically scoped to the tenant.
"""

import uuid
from contextvars import ContextVar

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

_tenant_ctx: ContextVar[uuid.UUID | None] = ContextVar("tenant_ctx", default=None)
_user_ctx: ContextVar[uuid.UUID | None] = ContextVar("user_ctx", default=None)


def get_current_org_id() -> uuid.UUID | None:
    return _tenant_ctx.get()


def get_current_user_id() -> uuid.UUID | None:
    return _user_ctx.get()


class TenantContextMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/health", "/api/v1/auth/login", "/api/v1/auth/register", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        token = self._extract_token(request)
        if token:
            try:
                payload = jwt.decode(
                    token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
                )
                org_id = payload.get("org_id")
                user_id = payload.get("user_id")
                if org_id:
                    _tenant_ctx.set(uuid.UUID(org_id))
                if user_id:
                    _user_ctx.set(uuid.UUID(user_id))
            except (JWTError, ValueError):
                pass

        response = await call_next(request)

        _tenant_ctx.set(None)
        _user_ctx.set(None)

        return response

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None
