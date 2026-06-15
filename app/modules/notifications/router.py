import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationResponse
from app.modules.notifications.service import NotificationService
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> NotificationService:
    return NotificationService(NotificationRepository(session))


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    current_user: AuthRequired,
    service: Annotated[NotificationService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_read: bool | None = None,
) -> PaginatedResponse:
    current_user.require("notification:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list_for_user(current_user.org_id, current_user.user_id, params, is_read)


@router.get("/unread-count")
async def unread_count(
    current_user: AuthRequired,
    service: Annotated[NotificationService, Depends(get_service)],
) -> dict:
    current_user.require("notification:read")
    count = await service.unread_count(current_user.org_id, current_user.user_id)
    return {"count": count}


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[NotificationService, Depends(get_service)],
) -> dict:
    current_user.require("notification:read")
    await service.mark_read(notification_id, current_user.user_id)
    return {"message": "Notification marked as read"}


@router.patch("/read-all")
async def mark_all_read(
    current_user: AuthRequired,
    service: Annotated[NotificationService, Depends(get_service)],
) -> dict:
    current_user.require("notification:read")
    count = await service.mark_all_read(current_user.org_id, current_user.user_id)
    return {"message": f"{count} notifications marked as read"}
