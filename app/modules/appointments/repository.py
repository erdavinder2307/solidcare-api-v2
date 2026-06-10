import uuid
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appointments.models import Appointment, AppointmentStatus
from app.shared.schemas.pagination import PaginationParams
from app.shared.utils.pagination import paginate


class AppointmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, appointment: Appointment) -> Appointment:
        self.session.add(appointment)
        await self.session.flush()
        await self.session.refresh(appointment)
        return appointment

    async def get_by_id(self, appointment_id: uuid.UUID, org_id: uuid.UUID) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment).where(
                Appointment.id == appointment_id,
                Appointment.organization_id == org_id,
                Appointment.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def check_slot_conflict(
        self,
        doctor_id: uuid.UUID,
        clinic_id: uuid.UUID,
        appointment_date: date,
        start_time: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = select(func.count(Appointment.id)).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.clinic_id == clinic_id,
                Appointment.appointment_date == appointment_date,
                Appointment.start_time == start_time,
                Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                Appointment.deleted_at.is_(None),
            )
        )
        if exclude_id:
            query = query.where(Appointment.id != exclude_id)
        result = await self.session.execute(query)
        return (result.scalar_one() or 0) > 0

    async def get_next_token(self, clinic_id: uuid.UUID, doctor_id: uuid.UUID, appointment_date: date) -> int:
        result = await self.session.execute(
            select(func.max(Appointment.token_number)).where(
                Appointment.clinic_id == clinic_id,
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appointment_date,
                Appointment.deleted_at.is_(None),
            )
        )
        max_token = result.scalar_one_or_none() or 0
        return max_token + 1

    async def list(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        clinic_id: uuid.UUID | None = None,
        doctor_id: uuid.UUID | None = None,
        patient_id: uuid.UUID | None = None,
        appointment_date: date | None = None,
        status: AppointmentStatus | None = None,
    ) -> tuple[list[Appointment], int]:
        query = select(Appointment).where(
            Appointment.organization_id == org_id,
            Appointment.deleted_at.is_(None),
        )
        if clinic_id:
            query = query.where(Appointment.clinic_id == clinic_id)
        if doctor_id:
            query = query.where(Appointment.doctor_id == doctor_id)
        if patient_id:
            query = query.where(Appointment.patient_id == patient_id)
        if appointment_date:
            query = query.where(Appointment.appointment_date == appointment_date)
        if status:
            query = query.where(Appointment.status == status)

        query = query.order_by(Appointment.appointment_date.desc(), Appointment.start_time)
        return await paginate(self.session, query, params)
