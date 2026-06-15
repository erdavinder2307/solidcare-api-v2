import uuid
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions.errors import ForbiddenError, UnauthorizedError
from app.core.security.jwt import decode_token

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
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.org_id = org_id
        self.clinic_ids = clinic_ids
        self.permissions = permissions
        self.roles = roles
        self.is_superadmin = is_superadmin

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
) -> CurrentUser:
    payload = decode_token(credentials.credentials)

    if payload.get("token_type") != "access":
        raise UnauthorizedError("Invalid token type")

    try:
        return CurrentUser(
            user_id=uuid.UUID(payload["user_id"]),
            email=payload["sub"],
            org_id=uuid.UUID(payload["org_id"]),
            clinic_ids=payload.get("clinic_ids", []),
            permissions=payload.get("permissions", []),
            roles=payload.get("roles", []),
            is_superadmin=payload.get("is_superadmin", False),
        )
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed token") from exc


def require_permission(permission: str):
    async def _checker(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        current_user.require(permission)
        return current_user
    return _checker


AuthRequired = Annotated[CurrentUser, Depends(get_current_user)]
