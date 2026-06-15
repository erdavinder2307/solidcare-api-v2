import uuid

from pydantic import BaseModel

from app.modules.clinics.models import ClinicType


class ClinicResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    clinic_type: ClinicType
    phone: str | None
    email: str | None
    city: str | None
    state: str | None
    is_active: bool

    model_config = {"from_attributes": True}
