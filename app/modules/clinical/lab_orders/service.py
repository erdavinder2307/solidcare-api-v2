import uuid
from datetime import UTC, datetime

from app.core.exceptions.errors import BusinessRuleError, NotFoundError
from app.modules.clinical.encounters.repository import EncounterRepository
from app.modules.clinical.lab_orders.models import LabOrder, LabOrderItem, LabOrderStatus
from app.modules.clinical.lab_orders.repository import LabOrderRepository
from app.modules.clinical.lab_orders.schemas import LabOrderCreate, LabResultCreate


class LabOrderService:
    def __init__(self, repository: LabOrderRepository, encounter_repository: EncounterRepository) -> None:
        self.repo = repository
        self.encounter_repo = encounter_repository

    async def create(self, org_id: uuid.UUID, data: LabOrderCreate, created_by: uuid.UUID) -> LabOrder:
        encounter = await self.encounter_repo.get_by_id(data.encounter_id, org_id)
        if not encounter:
            raise NotFoundError("Encounter", str(data.encounter_id))
        if encounter.patient_id != data.patient_id:
            raise BusinessRuleError("Patient does not match encounter")

        order = LabOrder(
            encounter_id=data.encounter_id,
            patient_id=data.patient_id,
            ordered_by_id=data.ordered_by_id,
            lab_name=data.lab_name,
            notes=data.notes,
            status=LabOrderStatus.ORDERED,
            ordered_at=datetime.now(UTC),
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        items = [LabOrderItem(**item.model_dump()) for item in data.items]
        return await self.repo.create(order, items)

    async def list_for_encounter(self, encounter_id: uuid.UUID, org_id: uuid.UUID) -> list[LabOrder]:
        encounter = await self.encounter_repo.get_by_id(encounter_id, org_id)
        if not encounter:
            raise NotFoundError("Encounter", str(encounter_id))
        return await self.repo.list_for_encounter(encounter_id)

    async def get(self, order_id: uuid.UUID, org_id: uuid.UUID) -> LabOrder:
        order = await self.repo.get_by_id(order_id)
        if not order:
            raise NotFoundError("LabOrder", str(order_id))
        # Verify org access via encounter
        encounter = await self.encounter_repo.get_by_id(order.encounter_id, org_id)
        if not encounter:
            raise NotFoundError("LabOrder", str(order_id))
        return order

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[LabOrder]:
        return await self.repo.list_for_patient(patient_id)

    async def add_result(
        self, order_id: uuid.UUID, org_id: uuid.UUID, results: list[LabResultCreate]
    ) -> LabOrder:
        from app.modules.clinical.lab_orders.models import LabResult
        order = await self.get(order_id, org_id)
        if order.status == LabOrderStatus.CANCELLED:
            raise BusinessRuleError("Cannot add results to a cancelled order")
        for r in results:
            result = LabResult(
                lab_order_id=order.id,
                patient_id=order.patient_id,
                **r.model_dump(),
            )
            self.repo.session.add(result)
        order.status = LabOrderStatus.RESULTED
        order.resulted_at = datetime.now(UTC)
        await self.repo.session.flush()
        return await self.repo.get_by_id(order.id)

    async def cancel(self, order_id: uuid.UUID, org_id: uuid.UUID) -> LabOrder:
        order = await self.get(order_id, org_id)
        if order.status in (LabOrderStatus.RESULTED, LabOrderStatus.CANCELLED):
            raise BusinessRuleError(f"Cannot cancel order with status {order.status.value}")
        order.status = LabOrderStatus.CANCELLED
        return order
