"""ICD-10 code search endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.clinical.diagnoses.models import ICD10Code

router = APIRouter(prefix="/icd10", tags=["ICD-10"])


class ICD10Result(BaseModel):
    code: str
    description: str
    category: str | None = None
    chapter: str | None = None
    is_billable: bool = True

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ICD10Result])
async def search_icd10(
    current_user: AuthRequired,
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(min_length=1, max_length=100, description="Search by code prefix or description"),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ICD10Result]:
    """
    Search ICD-10 codes by code prefix or description keyword.
    Returns up to `limit` results ordered by code.
    """
    current_user.require("encounter:read")
    term = q.strip()
    results = await session.execute(
        select(ICD10Code)
        .where(
            (ICD10Code.code.ilike(f"{term}%"))
            | (func.lower(ICD10Code.description).contains(term.lower()))
        )
        .order_by(ICD10Code.code)
        .limit(limit)
    )
    return [ICD10Result.model_validate(row) for row in results.scalars().all()]
