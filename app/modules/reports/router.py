import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.reports.service import ReportsService
from app.shared.utils.csv_export import csv_response, rows_to_csv

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

ReportKey = Literal[
    "opd-volume",
    "top-diagnoses",
    "outstanding",
    "revenue-trend",
    "appointment-types",
]

# (key, header) column maps per exportable report
_EXPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "opd-volume": [("date", "Date"), ("total", "Total appointments"), ("completed", "Completed")],
    "top-diagnoses": [("code", "Code"), ("description", "Description"), ("count", "Cases")],
    "outstanding": [
        ("invoice_number", "Invoice #"),
        ("invoice_date", "Invoice date"),
        ("due_date", "Due date"),
        ("patient_name", "Patient"),
        ("patient_phone", "Phone"),
        ("outstanding_amount", "Outstanding"),
        ("days_overdue", "Days overdue"),
        ("bucket", "Ageing bucket"),
    ],
    "revenue-trend": [("week", "Week starting"), ("revenue", "Revenue")],
    "appointment-types": [("type", "Appointment type"), ("count", "Count")],
}


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


@router.get("/doctors/{doctor_id}/summary")
async def doctor_performance_summary(
    doctor_id: uuid.UUID,
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> dict:
    current_user.require("report:read")
    return await service.doctor_summary(current_user.org_id, doctor_id, from_date, to_date)


@router.get("/billing/outstanding")
async def outstanding_aging_report(
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    as_of: date | None = None,
) -> dict:
    current_user.require("report:read")
    return await service.outstanding_aging(current_user.org_id, clinic_id, as_of)


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
    service: Annotated[ReportsService, Depends(get_reports_service)],
    from_date: date = Query(...),
    to_date: date = Query(...),
    clinic_id: uuid.UUID | None = None,
) -> dict:
    current_user.require("report:read")
    return await service.doctor_collection(current_user.org_id, from_date, to_date, clinic_id)


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


@router.get("/export/{report}")
async def export_report_csv(
    report: ReportKey,
    current_user: AuthRequired,
    service: Annotated[ReportsService, Depends(get_reports_service)],
    clinic_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    as_of: date | None = None,
    days: int = Query(default=90, ge=1, le=365),
    weeks: int = Query(default=8, ge=1, le=52),
    limit: int = Query(default=25, ge=1, le=200),
) -> StreamingResponse:
    """Download any of the dashboard/report datasets as CSV."""
    current_user.require("report:read")
    org_id = current_user.org_id

    if report == "opd-volume":
        rows = await service.opd_volume_trend(org_id, clinic_id, from_date, to_date)
    elif report == "top-diagnoses":
        rows = await service.top_diagnoses(org_id, clinic_id, days, limit)
    elif report == "outstanding":
        rows = (await service.outstanding_aging(org_id, clinic_id, as_of))["invoices"]
    elif report == "revenue-trend":
        rows = await service.revenue_trend(org_id, clinic_id, weeks)
    else:  # appointment-types
        rows = await service.appointment_type_distribution(org_id, clinic_id, days)

    csv_text = rows_to_csv(_EXPORT_COLUMNS[report], rows)
    return csv_response(csv_text, f"{report}-report")
