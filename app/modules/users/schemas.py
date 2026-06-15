import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.users.models import UserStatus


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    phone: str | None
    status: UserStatus
    roles: list[str] = []
    created_at: datetime
