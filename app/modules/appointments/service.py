import uuid
from datetime import datetime, timezone

from app.core.events.bus import event_bus
from app.core.events.handlers.notification_handler import AppointmentBooked, AppointmentCancelled
from app.core.exceptions.errors import BusinessRuleError, ConflictError, NotFoundError
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)
from app.modules.patients.repository import PatientRepository
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams


class AppointmentService:
    def __init__(self, repository: AppointmentRepository, patient_repository: PatientRepository) -> None:
        self.repo = repository
        self.patient_repo = patient_repository

    async def create(self, org_id: uuid.UUID, data: AppointmentCreate, created_by: uuid.UUID) -> Appointment:
        conflict = await self.repo.check_slot_conflict(
            data.doctor_id, data.clinic_id, data.appointment_date, data.start_time
        )
        if conflict:
            raise ConflictError("This time slot is already booked. Please select another slot.")

        token = await self.repo.get_next_token(data.clinic_id, data.doctor_id, data.appointment_date)
        appointment = Appointment(
            organization_id=org_id,
            token_number=token,
            created_by_id=created_by,
            **data.model_dump(),
        )
        appointment = await self.repo.create(appointment)

        patient = await self.patient_repo.get_by_id(appointment.patient_id, org_id)
        await event_bus.publish(AppointmentBooked(
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            clinic_id=appointment.clinic_id,
            appointment_date=str(appointment.appointment_date),
            appointment_time=appointment.start_time,
            patient_phone=patient.phone if patient else "",
            patient_email=patient.email if patient else None,
        ))

        return appointment

    async def get(self, appointment_id: uuid.UUID, org_id: uuid.UUID) -> Appointment:
        appointment = await self.repo.get_by_id(appointment_id, org_id)
        if not appointment:
            raise NotFoundError("Appointment", str(appointment_id))
        return appointment

    async def list(
        self,
        org_id: uuid.UUID,
        params: PaginationParams,
        **filters,
    ) -> PaginatedResponse:
        items, total = await self.repo.list(org_id, params, **filters)
        return PaginatedResponse.create(items, total, params)

    async def update(self, appointment_id: uuid.UUID, org_id: uuid.UUID, data: AppointmentUpdate) -> Appointment:
        appointment = await self.get(appointment_id, org_id)
        if appointment.status in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
            raise BusinessRuleError("Cannot modify a completed or cancelled appointment")

        if data.appointment_date or data.start_time:
            new_date = data.appointment_date or appointment.appointment_date
            new_time = data.start_time or appointment.start_time
            conflict = await self.repo.check_slot_conflict(
                appointment.doctor_id, appointment.clinic_id, new_date, new_time, appointment.id
            )
            if conflict:
                raise ConflictError("This slot is already booked")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(appointment, field, value)
        return appointment

    async def update_status(
        self, appointment_id: uuid.UUID, org_id: uuid.UUID, data: AppointmentStatusUpdate
    ) -> Appointment:
        appointment = await self.get(appointment_id, org_id)

        valid_transitions = {
            AppointmentStatus.SCHEDULED: [AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW],
            AppointmentStatus.CONFIRMED: [AppointmentStatus.CHECKED_IN, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW],
            AppointmentStatus.CHECKED_IN: [AppointmentStatus.IN_CONSULTATION, AppointmentStatus.CANCELLED],
            AppointmentStatus.IN_CONSULTATION: [AppointmentStatus.COMPLETED],
            AppointmentStatus.COMPLETED: [],
            AppointmentStatus.CANCELLED: [],
            AppointmentStatus.NO_SHOW: [],
        }

        if data.status not in valid_transitions.get(appointment.status, []):
            raise BusinessRuleError(f"Cannot transition from {appointment.status} to {data.status}")

        now = datetime.now(timezone.utc)
        appointment.status = data.status

        if data.status == AppointmentStatus.CHECKED_IN:
            appointment.checked_in_at = now
            if appointment.token_number is None:
                appointment.token_number = await self.repo.get_next_token(
                    appointment.clinic_id,
                    appointment.doctor_id,
                    appointment.appointment_date,
                )
        elif data.status == AppointmentStatus.IN_CONSULTATION:
            appointment.consultation_started_at = now
        elif data.status == AppointmentStatus.COMPLETED:
            appointment.consultation_ended_at = now
        elif data.status == AppointmentStatus.CANCELLED:
            appointment.cancelled_at = now
            appointment.cancellation_reason = data.cancellation_reason
            appointment.cancellation_notes = data.cancellation_notes
            await event_bus.publish(AppointmentCancelled(
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                patient_phone=(await self._patient_phone(org_id, appointment.patient_id)),
                reason=data.cancellation_notes,
            ))

        return appointment

    async def _patient_phone(self, org_id: uuid.UUID, patient_id: uuid.UUID) -> str:
        patient = await self.patient_repo.get_by_id(patient_id, org_id)
        return patient.phone if patient else ""
