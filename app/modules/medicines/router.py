from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.medicines.repository import MedicineRepository
from app.modules.medicines.schemas import MedicineResponse

router = APIRouter(prefix="/medicines", tags=["Medicines"])


@router.get("", response_model=list[MedicineResponse])
async def search_medicines(
    current_user: AuthRequired,
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[MedicineResponse]:
    current_user.require("prescription:read")
    if not q.strip():
        return []
    repo = MedicineRepository(session)
    medicines = await repo.search(q.strip(), limit)
    return [MedicineResponse.model_validate(m) for m in medicines]
