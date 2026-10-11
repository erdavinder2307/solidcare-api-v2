import uuid
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions.errors import ForbiddenError, UnauthorizedError
from app.core.security.jwt import decode_token
from app.database import get_db

security = HTTPBearer()


class CurrentUser:
    def __init__(
        self,
        user_id: uuid.UUID,
        email: str,
        org_id: uuid.UUID,
        clinic_ids: list[str],
        permissions: list[str],
        roles: list[str],
        is_superadmin: bool = False,
        memberships: list[dict] | None = None,
    ) -> None:
        self.user_id = user_id
        self.email = email
        # `org_id` is the ACTIVE org for this request/token — driven by
        # `active_org_id` on the JWT (see core/security/jwt.py). Every existing
        # `current_user.org_id` usage across the codebase therefore already
        # respects org-switching (F2) with no per-module changes required.
        self.org_id = org_id
        self.clinic_ids = clinic_ids
        self.permissions = permissions
        self.roles = roles
        self.is_superadmin = is_superadmin
        self.memberships = memberships or []

    def can(self, permission: str) -> bool:
        return (
            self.is_superadmin
            or "superadmin" in self.roles
            or permission in self.permissions
        )

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise ForbiddenError(f"Missing required permission: {permission}")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser:
    payload = decode_token(credentials.credentials)

    if payload.get("token_type") != "access":
        raise UnauthorizedError("Invalid token type")

    try:
        # `active_org_id` may be absent on tokens issued before this field existed
        # (pre-F2) — fall back to `org_id` so those tokens keep working until they
        # expire naturally rather than forcing every open session to re-login.
        active_org_id = payload.get("active_org_id") or payload["org_id"]
        org_uuid = uuid.UUID(active_org_id)
        current_user = CurrentUser(
            user_id=uuid.UUID(payload["user_id"]),
            email=payload["sub"],
            org_id=org_uuid,
            clinic_ids=payload.get("clinic_ids", []),
            permissions=payload.get("permissions", []),
            roles=payload.get("roles", []),
            is_superadmin=payload.get("is_superadmin", False),
            memberships=payload.get("memberships", []),
        )
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed token") from exc

    # Scope this request's DB session to the active org for Postgres Row-Level
    # Security (see ROADMAP.md F6 / docs/adr/002-shared-schema-tenancy.md).
    # `session` here is the SAME AsyncSession instance every other dependency in
    # this request receives from `Depends(get_db)` — FastAPI caches dependency
    # results per-request — so this makes RLS apply automatically to every
    # authenticated route with zero changes to any router module.
    #
    # `SET LOCAL` scopes to the current transaction only; it is cleared the
    # moment `get_db()` commits/rolls back at the end of the request, so it can
    # never leak between requests sharing a pooled connection. `org_uuid` is a
    # `uuid.UUID` instance (validated above — construction raises on anything
    # that isn't canonical UUID syntax), so interpolating its string form here
    # cannot be an injection vector: Postgres does not support bind parameters
    # in `SET` statements, so this is the standard pattern for this exact case.
    await session.execute(text(f"SET LOCAL app.current_org_id = '{org_uuid}'"))

    return current_user


def require_permission(permission: str):
    async def _checker(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        current_user.require(permission)
        return current_user
    return _checker


AuthRequired = Annotated[CurrentUser, Depends(get_current_user)]
