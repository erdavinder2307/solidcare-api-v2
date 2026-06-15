import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogResponse
from app.modules.audit.service import AuditService
from app.modules.auth.dependencies import AuthRequired
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuditService:
    return AuditService(AuditRepository(session))


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    current_user: AuthRequired,
    service: Annotated[AuditService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> PaginatedResponse:
    current_user.require("audit:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list_logs(
        current_user.org_id,
        params,
        user_id=user_id,
        resource_type=resource_type,
        action=action,
        from_date=from_date,
        to_date=to_date,
    )
