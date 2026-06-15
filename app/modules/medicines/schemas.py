import uuid

from pydantic import BaseModel

from app.modules.medicines.models import DosageForm


class MedicineResponse(BaseModel):
    id: uuid.UUID
    generic_name: str
    brand_name: str | None
    manufacturer: str | None
    dosage_form: DosageForm
    strength: str | None
    is_active: bool
    is_scheduled: bool = False
    schedule_class: str | None = None  # H, H1, X, etc.

    model_config = {"from_attributes": True}
