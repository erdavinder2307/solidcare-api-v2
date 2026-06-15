import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserListItem

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserListItem])
async def list_users(
    current_user: AuthRequired,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserListItem]:
    current_user.require("doctor:read")
    users = await UserRepository(session).list_for_org(current_user.org_id)
    return [
        UserListItem(
            id=u.id,
            email=u.email,
            first_name=u.first_name,
            last_name=u.last_name,
            phone=u.phone,
            status=u.status,
            roles=[ur.role.slug for ur in u.user_roles if ur.role],
            created_at=u.created_at,
        )
        for u in users
    ]
