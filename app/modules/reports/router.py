import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


@router.get("/dashboard/kpis")
async def get_dashboard_kpis(
    current_user: AuthRequired,
    clinic_id: uuid.UUID | None = None,
    report_date: date | None = None,
) -> dict:
    current_user.require("report:read")
    return {
        "today_appointments": 0,
        "today_revenue": 0.0,
        "new_patients_today": 0,
        "pending_bills": 0,
        "checked_in_patients": 0,
        "completed_consultations": 0,
    }


@router.get("/appointments/daily-opd")
async def daily_opd_report(
    current_user: AuthRequired,
    clinic_id: uuid.UUID,
    report_date: date,
) -> dict:
    current_user.require("report:read")
    return {
        "date": str(report_date),
        "clinic_id": str(clinic_id),
        "total_appointments": 0,
        "completed": 0,
        "cancelled": 0,
        "no_show": 0,
        "doctor_wise": [],
    }


@router.get("/billing/revenue")
async def revenue_report(
    current_user: AuthRequired,
    clinic_id: uuid.UUID | None = None,
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> dict:
    current_user.require("report:read")
    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "total_revenue": 0.0,
        "total_collected": 0.0,
        "outstanding": 0.0,
        "payment_method_breakdown": {},
        "daily_breakdown": [],
    }


@router.get("/patients/demographics")
async def patient_demographics(
    current_user: AuthRequired,
    clinic_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    current_user.require("report:read")
    return {
        "total_patients": 0,
        "new_patients": 0,
        "gender_distribution": {},
        "age_distribution": {},
        "city_distribution": {},
    }


@router.get("/doctors/collection")
async def doctor_collection_report(
    current_user: AuthRequired,
    clinic_id: uuid.UUID | None = None,
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> dict:
    current_user.require("report:read")
    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "doctors": [],
    }
