import csv
import io
import uuid

from app.modules.audit.repository import AuditRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

EXPORT_COLUMNS = [
    "created_at",
    "user_email",
    "action",
    "resource_type",
    "resource_id",
    "success",
    "ip_address",
    "http_method",
    "endpoint",
    "failure_reason",
]


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

    async def export_csv(self, org_id: uuid.UUID, **filters) -> str:
        """Return matching audit logs as a CSV string (newest first)."""
        logs = await self.repo.list_all_for_export(org_id, **filters)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        for log in logs:
            writer.writerow([
                log.created_at.isoformat() if log.created_at else "",
                log.user_email or "",
                log.action or "",
                log.resource_type or "",
                log.resource_id or "",
                "" if log.success is None else ("success" if log.success else "failure"),
                log.ip_address or "",
                log.http_method or "",
                log.endpoint or "",
                log.failure_reason or "",
            ])
        return buffer.getvalue()
