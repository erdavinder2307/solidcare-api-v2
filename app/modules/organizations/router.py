import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    current_user: AuthRequired,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    result = await session.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        from app.core.exceptions.errors import NotFoundError
        raise NotFoundError("Organization", str(current_user.org_id))
    return OrganizationResponse.model_validate(org)
