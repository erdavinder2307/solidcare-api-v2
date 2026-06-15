from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.medicines.models import Medicine


class MedicineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, limit: int = 20) -> list[Medicine]:
        pattern = f"%{query.lower()}%"
        result = await self.session.execute(
            select(Medicine)
            .where(
                Medicine.is_active == True,  # noqa: E712
                Medicine.deleted_at.is_(None),
                or_(
                    Medicine.generic_name.ilike(pattern),
                    Medicine.brand_name.ilike(pattern),
                ),
            )
            .order_by(Medicine.generic_name)
            .limit(limit)
        )
        return list(result.scalars().all())
