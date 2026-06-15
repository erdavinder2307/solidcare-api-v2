import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.modules.audit.models import AuditAction


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    organization_id: uuid.UUID | None
    user_id: uuid.UUID | None
    user_email: str | None
    action: AuditAction
    resource_type: str
    resource_id: str | None
    endpoint: str | None
    http_method: str | None
    success: bool | None

    model_config = {"from_attributes": True}
