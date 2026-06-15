import uuid

from app.modules.audit.repository import AuditRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repo = repository

    async def list_logs(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        **filters,
    ) -> PaginatedResponse:
        items, total = await self.repo.list_logs(org_id, params.page, params.page_size, **filters)
        return PaginatedResponse.create(items, total, params)
