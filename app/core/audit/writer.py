"""Append-only audit log writer."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.modules.audit.models import AuditAction, AuditLog

logger = logging.getLogger("audit")


def extract_actor_from_request(request: Request) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, None, None
    try:
        payload = jwt.decode(
            auth[7:], settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        org_id = uuid.UUID(payload["org_id"]) if payload.get("org_id") else None
        user_id = uuid.UUID(payload["user_id"]) if payload.get("user_id") else None
        email = payload.get("sub")
        return org_id, user_id, email
    except (JWTError, ValueError, KeyError):
        return None, None, None


def parse_phi_resource(path: str) -> tuple[str, str | None]:
    """Map API path to resource_type and optional resource_id."""
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "v1":
        return "unknown", None

    segment = parts[2]
    type_map = {
        "patients": "patient",
        "encounters": "encounter",
        "prescriptions": "prescription",
        "clinical": "clinical",
    }
    resource_type = type_map.get(segment, segment.rstrip("s"))
    resource_id = None
    if len(parts) >= 4:
        candidate = parts[3]
        try:
            uuid.UUID(candidate)
            resource_id = candidate
        except ValueError:
            pass
    return resource_type, resource_id


def action_for_method(method: str) -> AuditAction:
    return {
        "GET": AuditAction.READ,
        "POST": AuditAction.CREATE,
        "PUT": AuditAction.UPDATE,
        "PATCH": AuditAction.UPDATE,
        "DELETE": AuditAction.DELETE,
    }.get(method.upper(), AuditAction.READ)


async def record_audit(
    session: AsyncSession,
    *,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None = None,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    endpoint: str | None = None,
    http_method: str | None = None,
    success: bool = True,
    failure_reason: str | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            http_method=http_method,
            success=success,
            failure_reason=failure_reason,
            extra=extra,
        )
    )


async def persist_request_audit(request: Request, *, status_code: int, elapsed_ms: float) -> None:
    """Persist PHI access audit entry using a standalone DB session."""
    from app.database import AsyncSessionLocal

    org_id, user_id, user_email = extract_actor_from_request(request)
    resource_type, resource_id = parse_phi_resource(request.url.path)
    ip = request.client.host if request.client else None

    async with AsyncSessionLocal() as session:
        try:
            await record_audit(
                session,
                action=action_for_method(request.method),
                resource_type=resource_type,
                resource_id=resource_id,
                organization_id=org_id,
                user_id=user_id,
                user_email=user_email,
                ip_address=ip,
                user_agent=request.headers.get("user-agent"),
                endpoint=request.url.path,
                http_method=request.method,
                success=status_code < 400,
                failure_reason=None if status_code < 400 else f"HTTP {status_code}",
                extra={"elapsed_ms": elapsed_ms},
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to persist audit log for %s", request.url.path)
