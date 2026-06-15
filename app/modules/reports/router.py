import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.reports.service import ReportsService

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


def get_reports_service(session: Annotated[AsyncSession, Depends(get_db)]) -> ReportsService:
    return ReportsService(session)


@router.get("/dashboard/kpis")
async def get_dashboard_kpis(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    report_date: date | None = None,
) -> dict:
    current_user.require("report:read")
    return await service.dashboard_kpis(current_user.org_id, clinic_id, report_date)


@router.get("/appointments/daily-opd")
async def daily_opd_report(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID,
    report_date: date,
) -> dict:
    current_user.require("report:read")
    return await service.daily_opd(current_user.org_id, clinic_id, report_date)


@router.get("/billing/revenue")
async def revenue_report(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    from_date: date = Query(...),
    to_date: date = Query(...),
    clinic_id: uuid.UUID | None = None,
) -> dict:
    current_user.require("report:read")
    return await service.revenue_report(current_user.org_id, from_date, to_date, clinic_id)


@router.get("/patients/demographics")
async def patient_demographics(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
) -> dict:
    current_user.require("report:read")
    return await service.patient_demographics(current_user.org_id, clinic_id)


@router.get("/doctors/collection")
async def doctor_collection_report(
    current_user: AuthRequired,
    from_date: date = Query(...),
    to_date: date = Query(...),
    clinic_id: uuid.UUID | None = None,
) -> dict:
    current_user.require("report:read")
    return {"from_date": str(from_date), "to_date": str(to_date), "doctors": []}


@router.get("/appointments/trend")
async def appointments_trend(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=7, le=90),
) -> list[dict]:
    current_user.require("report:read")
    return await service.appointments_trend(current_user.org_id, clinic_id, days)


@router.get("/billing/revenue-trend")
async def revenue_trend(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    weeks: int = Query(default=8, ge=4, le=52),
) -> list[dict]:
    current_user.require("report:read")
    return await service.revenue_trend(current_user.org_id, clinic_id, weeks)


@router.get("/appointments/type-distribution")
async def appointment_type_distribution(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=7, le=90),
) -> list[dict]:
    current_user.require("report:read")
    return await service.appointment_type_distribution(current_user.org_id, clinic_id, days)


@router.get("/diagnoses/top")
async def top_diagnoses(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    days: int = Query(default=30, ge=7, le=365),
    limit: int = Query(default=10, ge=5, le=25),
) -> list[dict]:
    current_user.require("report:read")
    return await service.top_diagnoses(current_user.org_id, clinic_id, days, limit)


@router.get("/appointments/opd-volume")
async def opd_volume_trend(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    current_user.require("report:read")
    return await service.opd_volume_trend(current_user.org_id, clinic_id, from_date, to_date)
