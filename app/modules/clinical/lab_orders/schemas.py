import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.clinical.lab_orders.models import LabOrderStatus


class LabOrderItemCreate(BaseModel):
    test_name: str
    test_code: str | None = None
    notes: str | None = None


class LabOrderCreate(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    ordered_by_id: uuid.UUID
    lab_name: str | None = None
    notes: str | None = None
    items: list[LabOrderItemCreate] = Field(min_length=1)


class LabOrderItemResponse(BaseModel):
    id: uuid.UUID
    test_name: str
    test_code: str | None
    notes: str | None

    model_config = {"from_attributes": True}


class LabOrderResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    ordered_by_id: uuid.UUID
    lab_name: str | None
    notes: str | None
    status: LabOrderStatus
    ordered_at: datetime
    items: list[LabOrderItemResponse] = []

    model_config = {"from_attributes": True}


class LabResultCreate(BaseModel):
    test_name: str
    value: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    is_abnormal: bool | None = None
    notes: str | None = None


class LabResultResponse(BaseModel):
    id: uuid.UUID
    test_name: str
    value: str | None
    unit: str | None
    reference_range: str | None
    is_abnormal: bool | None
    notes: str | None

    model_config = {"from_attributes": True}


class LabOrderWithResultsResponse(LabOrderResponse):
    results: list[LabResultResponse] = []
