import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.clinics.models import Clinic
from app.modules.doctors.models import DayOfWeek, Doctor, DoctorClinicAssignment, DoctorSchedule
from app.modules.users.models import Role, User, UserRole


class DoctorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, doctor: Doctor) -> Doctor:
        self.session.add(doctor)
        await self.session.flush()
        await self.session.refresh(doctor)
        return doctor

    async def get_by_id(self, doctor_id: uuid.UUID, org_id: uuid.UUID) -> Doctor | None:
        result = await self.session.execute(
            select(Doctor)
            .where(
                Doctor.id == doctor_id,
                Doctor.organization_id == org_id,
                Doctor.deleted_at.is_(None),
            )
            .options(selectinload(Doctor.user))
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Doctor | None:
        result = await self.session.execute(
            select(Doctor).where(Doctor.user_id == user_id, Doctor.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_doctors(self, org_id: uuid.UUID) -> list[Doctor]:
        result = await self.session.execute(
            select(Doctor)
            .where(Doctor.organization_id == org_id, Doctor.deleted_at.is_(None))
            .options(selectinload(Doctor.user))
            .order_by(Doctor.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_clinic_by_id(self, clinic_id: uuid.UUID, org_id: uuid.UUID) -> Clinic | None:
        result = await self.session.execute(
            select(Clinic).where(
                Clinic.id == clinic_id,
                Clinic.organization_id == org_id,
                Clinic.deleted_at.is_(None),
                Clinic.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str, org_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.email == email.lower(),
                User.organization_id == org_id,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_role_by_slug(self, org_id: uuid.UUID, slug: str) -> Role | None:
        result = await self.session.execute(
            select(Role).where(
                Role.slug == slug,
                Role.organization_id == org_id,
                Role.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def assign_role(self, user_role: UserRole) -> UserRole:
        self.session.add(user_role)
        await self.session.flush()
        return user_role

    async def get_schedules(self, doctor_id: uuid.UUID, clinic_id: uuid.UUID | None = None) -> list[DoctorSchedule]:
        query = select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.is_active == True,  # noqa: E712
            DoctorSchedule.deleted_at.is_(None),
        )
        if clinic_id:
            query = query.where(DoctorSchedule.clinic_id == clinic_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def add_schedule(self, schedule: DoctorSchedule) -> DoctorSchedule:
        self.session.add(schedule)
        await self.session.flush()
        await self.session.refresh(schedule)
        return schedule

    async def add_clinic_assignment(self, assignment: DoctorClinicAssignment) -> DoctorClinicAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def get_available_slots(
        self, doctor_id: uuid.UUID, clinic_id: uuid.UUID, target_date: date
    ) -> list[str]:
        """Return list of available HH:MM time slots."""
        day_enum = DayOfWeek[target_date.strftime("%A").upper()]
        result = await self.session.execute(
            select(DoctorSchedule).where(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.clinic_id == clinic_id,
                DoctorSchedule.day_of_week == day_enum,
                DoctorSchedule.is_active == True,  # noqa: E712
                DoctorSchedule.deleted_at.is_(None),
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return []

        from datetime import datetime, timedelta
        slots = []
        start = datetime.strptime(schedule.start_time, "%H:%M:%S")
        end = datetime.strptime(schedule.end_time, "%H:%M:%S")
        delta = timedelta(minutes=schedule.slot_duration_minutes)
        current = start
        while current + delta <= end:
            slots.append(current.strftime("%H:%M"))
            current += delta
        return slots
