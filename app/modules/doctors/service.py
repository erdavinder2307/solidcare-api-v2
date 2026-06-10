import uuid
from datetime import date

from app.core.exceptions.errors import ConflictError, NotFoundError
from app.modules.doctors.models import Doctor, DoctorClinicAssignment, DoctorSchedule
from app.modules.doctors.repository import DoctorRepository
from app.modules.doctors.schemas import ClinicAssignmentCreate, DoctorCreate, DoctorUpdate, ScheduleCreate


class DoctorService:
    def __init__(self, repository: DoctorRepository) -> None:
        self.repo = repository

    async def create(self, org_id: uuid.UUID, data: DoctorCreate, created_by: uuid.UUID) -> Doctor:
        existing = await self.repo.get_by_user_id(data.user_id)
        if existing:
            raise ConflictError("A doctor profile already exists for this user")

        doctor = Doctor(organization_id=org_id, created_by_id=created_by, **data.model_dump())
        return await self.repo.create(doctor)

    async def get(self, doctor_id: uuid.UUID, org_id: uuid.UUID) -> Doctor:
        doctor = await self.repo.get_by_id(doctor_id, org_id)
        if not doctor:
            raise NotFoundError("Doctor", str(doctor_id))
        return doctor

    async def list_doctors(self, org_id: uuid.UUID) -> list[Doctor]:
        return await self.repo.list_doctors(org_id)

    async def update(self, doctor_id: uuid.UUID, org_id: uuid.UUID, data: DoctorUpdate) -> Doctor:
        doctor = await self.get(doctor_id, org_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(doctor, field, value)
        return doctor

    async def add_schedule(self, doctor_id: uuid.UUID, org_id: uuid.UUID, data: ScheduleCreate) -> DoctorSchedule:
        await self.get(doctor_id, org_id)
        schedule = DoctorSchedule(doctor_id=doctor_id, **data.model_dump())
        return await self.repo.add_schedule(schedule)

    async def get_schedules(self, doctor_id: uuid.UUID, org_id: uuid.UUID, clinic_id: uuid.UUID | None = None) -> list[DoctorSchedule]:
        await self.get(doctor_id, org_id)
        return await self.repo.get_schedules(doctor_id, clinic_id)

    async def assign_to_clinic(self, doctor_id: uuid.UUID, org_id: uuid.UUID, data: ClinicAssignmentCreate) -> DoctorClinicAssignment:
        await self.get(doctor_id, org_id)
        assignment = DoctorClinicAssignment(doctor_id=doctor_id, **data.model_dump())
        return await self.repo.add_clinic_assignment(assignment)

    async def get_available_slots(
        self, doctor_id: uuid.UUID, org_id: uuid.UUID, clinic_id: uuid.UUID, target_date: date
    ) -> list[str]:
        await self.get(doctor_id, org_id)
        return await self.repo.get_available_slots(doctor_id, clinic_id, target_date)
