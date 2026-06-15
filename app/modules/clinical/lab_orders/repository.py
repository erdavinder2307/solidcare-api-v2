import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.clinical.lab_orders.models import LabOrder, LabOrderItem


class LabOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, order: LabOrder, items: list[LabOrderItem]) -> LabOrder:
        self.session.add(order)
        await self.session.flush()
        for item in items:
            item.lab_order_id = order.id
            self.session.add(item)
        await self.session.flush()
        return await self.get_by_id(order.id)

    async def get_by_id(self, order_id: uuid.UUID) -> LabOrder | None:
        result = await self.session.execute(
            select(LabOrder)
            .where(LabOrder.id == order_id, LabOrder.deleted_at.is_(None))
            .options(selectinload(LabOrder.items))
        )
        return result.scalar_one_or_none()

    async def list_for_encounter(self, encounter_id: uuid.UUID) -> list[LabOrder]:
        result = await self.session.execute(
            select(LabOrder)
            .where(LabOrder.encounter_id == encounter_id, LabOrder.deleted_at.is_(None))
            .options(selectinload(LabOrder.items))
            .order_by(LabOrder.ordered_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_patient(self, patient_id: uuid.UUID) -> list[LabOrder]:
        result = await self.session.execute(
            select(LabOrder)
            .where(LabOrder.patient_id == patient_id, LabOrder.deleted_at.is_(None))
            .options(selectinload(LabOrder.items), selectinload(LabOrder.results))
            .order_by(LabOrder.ordered_at.desc())
        )
        return list(result.scalars().all())
