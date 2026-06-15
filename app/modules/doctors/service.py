import uuid
from datetime import date

from app.core.exceptions.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.security.password import hash_password
from app.modules.doctors.models import DayOfWeek, Doctor, DoctorClinicAssignment, DoctorSchedule, DoctorStatus
from app.modules.doctors.repository import DoctorRepository
from app.modules.doctors.schemas import ClinicAssignmentCreate, DoctorCreate, DoctorRegisterCreate, DoctorUpdate, ScheduleCreate
from app.modules.users.models import User, UserRole, UserStatus


class DoctorService:
    def __init__(self, repository: DoctorRepository) -> None:
        self.repo = repository

    async def create(self, org_id: uuid.UUID, data: DoctorCreate, created_by: uuid.UUID) -> Doctor:
        existing = await self.repo.get_by_user_id(data.user_id)
        if existing:
            raise ConflictError("A doctor profile already exists for this user")

        doctor = Doctor(organization_id=org_id, created_by_id=created_by, **data.model_dump())
        return await self.repo.create(doctor)

    async def register(
        self, org_id: uuid.UUID, data: DoctorRegisterCreate, created_by: uuid.UUID
    ) -> Doctor:
        existing_user = await self.repo.get_user_by_email(data.email, org_id)
        if existing_user:
            raise ConflictError(f"A user with email {data.email} already exists")

        doctor_role = await self.repo.get_role_by_slug(org_id, "doctor")
        if not doctor_role:
            raise BusinessRuleError("Doctor role is not configured for this organization")

        clinic = await self.repo.get_clinic_by_id(data.clinic_id, org_id)
        if not clinic:
            raise NotFoundError(
                "Clinic",
                f"{data.clinic_id} — run migrations or scripts/seed_dev_admin.sql to seed the demo clinic",
            )

        user = User(
            organization_id=org_id,
            email=data.email.lower(),
            phone=data.phone,
            first_name=data.first_name,
            last_name=data.last_name,
            hashed_password=hash_password(data.password),
            status=UserStatus.ACTIVE,
            email_verified=True,
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        user = await self.repo.create_user(user)
        await self.repo.assign_role(UserRole(user_id=user.id, role_id=doctor_role.id, clinic_id=data.clinic_id))

        doctor = Doctor(
            organization_id=org_id,
            user_id=user.id,
            registration_number=data.registration_number,
            registration_council=data.registration_council,
            qualifications=data.qualifications,
            specializations=data.specializations,
            years_of_experience=data.years_of_experience,
            consultation_fee=data.consultation_fee,
            follow_up_fee=data.follow_up_fee,
            bio=data.bio,
            languages=data.languages,
            status=DoctorStatus.ACTIVE,
            created_by_id=created_by,
            updated_by_id=created_by,
        )
        doctor = await self.repo.create(doctor)

        await self.repo.add_clinic_assignment(
            DoctorClinicAssignment(
                doctor_id=doctor.id,
                clinic_id=data.clinic_id,
                is_primary=True,
                consultation_fee_override=data.consultation_fee,
            )
        )

        for day in (
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
        ):
            await self.repo.add_schedule(
                DoctorSchedule(
                    doctor_id=doctor.id,
                    clinic_id=data.clinic_id,
                    day_of_week=day,
                    start_time="09:00:00",
                    end_time="17:00:00",
                    slot_duration_minutes=15,
                    is_active=True,
                )
            )

        loaded = await self.repo.get_by_id(doctor.id, org_id)
        return loaded or doctor

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
