import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.appointments.models import AppointmentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentListItem,
    AppointmentResponse,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)
from app.modules.appointments.service import AppointmentService
from app.modules.auth.dependencies import AuthRequired
from app.shared.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AppointmentService:
    return AppointmentService(AppointmentRepository(session))


@router.post("", response_model=AppointmentResponse, status_code=201)
async def create_appointment(
    payload: AppointmentCreate,
    current_user: AuthRequired,
    service: Annotated[AppointmentService, Depends(get_service)],
) -> AppointmentResponse:
    current_user.require("appointment:create")
    appt = await service.create(current_user.org_id, payload, current_user.user_id)
    return AppointmentResponse.model_validate(appt)


@router.get("", response_model=PaginatedResponse[AppointmentListItem])
async def list_appointments(
    current_user: AuthRequired,
    service: Annotated[AppointmentService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    clinic_id: uuid.UUID | None = None,
    doctor_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    appointment_date: date | None = None,
    status: AppointmentStatus | None = None,
) -> PaginatedResponse:
    current_user.require("appointment:read")
    params = PaginationParams(page=page, page_size=page_size)
    return await service.list(
        current_user.org_id, params,
        clinic_id=clinic_id, doctor_id=doctor_id, patient_id=patient_id,
        appointment_date=appointment_date, status=status,
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[AppointmentService, Depends(get_service)],
) -> AppointmentResponse:
    current_user.require("appointment:read")
    appt = await service.get(appointment_id, current_user.org_id)
    return AppointmentResponse.model_validate(appt)


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    current_user: AuthRequired,
    service: Annotated[AppointmentService, Depends(get_service)],
) -> AppointmentResponse:
    current_user.require("appointment:update")
    appt = await service.update(appointment_id, current_user.org_id, payload)
    return AppointmentResponse.model_validate(appt)


@router.patch("/{appointment_id}/status", response_model=AppointmentResponse)
async def update_status(
    appointment_id: uuid.UUID,
    payload: AppointmentStatusUpdate,
    current_user: AuthRequired,
    service: Annotated[AppointmentService, Depends(get_service)],
) -> AppointmentResponse:
    current_user.require("appointment:update")
    appt = await service.update_status(appointment_id, current_user.org_id, payload)
    return AppointmentResponse.model_validate(appt)
