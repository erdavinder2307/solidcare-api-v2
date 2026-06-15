from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.schemas.pagination import PaginationParams


async def paginate(
    session: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> tuple[list, int]:
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    result = await session.execute(
        query.offset(params.offset).limit(params.page_size)
    )
    items = result.scalars().all()

    return list(items), total
