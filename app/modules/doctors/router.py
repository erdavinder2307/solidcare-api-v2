import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.doctors.repository import DoctorRepository
from app.modules.doctors.schemas import (
    ClinicAssignmentCreate,
    DoctorCreate,
    DoctorResponse,
    DoctorUpdate,
    ScheduleCreate,
    ScheduleResponse,
)
from app.modules.doctors.service import DoctorService

router = APIRouter(prefix="/doctors", tags=["Doctors"])


def get_doctor_service(session: Annotated[AsyncSession, Depends(get_db)]) -> DoctorService:
    return DoctorService(DoctorRepository(session))


@router.post("", response_model=DoctorResponse, status_code=201)
async def create_doctor(
    payload: DoctorCreate,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> DoctorResponse:
    current_user.require("doctor:create")
    doctor = await service.create(current_user.org_id, payload, current_user.user_id)
    return DoctorResponse.model_validate(doctor)


@router.get("", response_model=list[DoctorResponse])
async def list_doctors(
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> list[DoctorResponse]:
    current_user.require("doctor:read")
    doctors = await service.list_doctors(current_user.org_id)
    return [DoctorResponse.model_validate(d) for d in doctors]


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> DoctorResponse:
    current_user.require("doctor:read")
    doctor = await service.get(doctor_id, current_user.org_id)
    return DoctorResponse.model_validate(doctor)


@router.patch("/{doctor_id}", response_model=DoctorResponse)
async def update_doctor(
    doctor_id: uuid.UUID,
    payload: DoctorUpdate,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> DoctorResponse:
    current_user.require("doctor:update")
    doctor = await service.update(doctor_id, current_user.org_id, payload)
    return DoctorResponse.model_validate(doctor)


@router.post("/{doctor_id}/schedules", response_model=ScheduleResponse, status_code=201)
async def add_schedule(
    doctor_id: uuid.UUID,
    payload: ScheduleCreate,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> ScheduleResponse:
    current_user.require("doctor:update")
    schedule = await service.add_schedule(doctor_id, current_user.org_id, payload)
    return ScheduleResponse.model_validate(schedule)


@router.get("/{doctor_id}/schedules", response_model=list[ScheduleResponse])
async def get_schedules(
    doctor_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
    clinic_id: uuid.UUID | None = Query(default=None),
) -> list[ScheduleResponse]:
    current_user.require("doctor:read")
    schedules = await service.get_schedules(doctor_id, current_user.org_id, clinic_id)
    return [ScheduleResponse.model_validate(s) for s in schedules]


@router.get("/{doctor_id}/available-slots")
async def get_available_slots(
    doctor_id: uuid.UUID,
    clinic_id: uuid.UUID,
    target_date: date,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> dict:
    current_user.require("appointment:create")
    slots = await service.get_available_slots(doctor_id, current_user.org_id, clinic_id, target_date)
    return {"date": str(target_date), "slots": slots}


@router.post("/{doctor_id}/clinic-assignments", status_code=201)
async def assign_to_clinic(
    doctor_id: uuid.UUID,
    payload: ClinicAssignmentCreate,
    current_user: AuthRequired,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> dict:
    current_user.require("doctor:update")
    await service.assign_to_clinic(doctor_id, current_user.org_id, payload)
    return {"message": "Doctor assigned to clinic"}
