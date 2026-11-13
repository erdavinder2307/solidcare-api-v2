import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions.errors import ForbiddenError
from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_demo: bool = False

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


class DemoResetResponse(BaseModel):
    status: str
    deleted: dict[str, int]
    seeded: dict[str, int]


def _is_org_admin(user) -> bool:
    return user.is_superadmin or bool({"admin", "superadmin"} & set(user.roles))


@router.post("/current/demo-reset", response_model=DemoResetResponse)
async def reset_demo_data(
    current_user: AuthRequired,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DemoResetResponse:
    """Reset demo data: restore the demo clinic to its seeded state (SE-4193, D4).

    Admins of the demo org only; any other org gets 403 and nothing is touched.
    POST (not DELETE) because DemoGuardMiddleware blocks every DELETE in a demo org.
    """
    if not _is_org_admin(current_user):
        raise ForbiddenError("Only an organization admin can reset demo data")
    result = await session.execute(
        select(Organization.is_demo).where(Organization.id == current_user.org_id)
    )
    if result.scalar_one_or_none() is not True:
        raise ForbiddenError("Only the demo clinic can be reset")
    # Imported here so Faker (used by the seed) is only loaded when a reset runs.
    from app.core.demo_tenant.reset import DemoResetRefused, reset_demo_tenant

    try:
        outcome = await reset_demo_tenant(session, current_user.org_id)
    except DemoResetRefused as exc:
        raise ForbiddenError(str(exc)) from exc
    return DemoResetResponse(status="reset", **outcome)
