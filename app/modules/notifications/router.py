import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.notifications.models import NotificationChannel, NotificationStatus, NotificationType

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    current_user: AuthRequired,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_read: bool | None = None,
) -> dict:
    current_user.require("notification:read")
    return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: AuthRequired,
) -> dict:
    return {"message": "Notification marked as read"}


@router.patch("/read-all")
async def mark_all_read(current_user: AuthRequired) -> dict:
    return {"message": "All notifications marked as read"}
