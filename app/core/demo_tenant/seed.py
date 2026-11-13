"""Demo-tenant seed core (SE-4193, D1).

Builds and upserts the synthetic demo tenant: one demo organization
(``is_demo = TRUE``) with a clinic, demo staff logins (admin, two doctors,
receptionist) and about 50 synthetic patients with roughly six months of history
(appointments, encounters, prescriptions, invoices and payments).

Lives in the app package so it ships in the deploy package and can be used by the
reset (core/demo_tenant/reset.py), the nightly Celery task and the API endpoint.
The CLI is ``python -m scripts.seed_demo_tenant``.

Safety:
- Only ever writes rows for the fixed demo org/clinic below. Every row in the plan is
  checked against those ids before anything is written.
- Refuses to run when an organization with the demo id or slug exists but is not
  flagged ``is_demo``.
- Idempotent: every row has a deterministic id, and rows are upserted on id, so a
  re-run refreshes the seeded rows in place. It never deletes anything.
- All data is fake: names come from Faker with a fixed seed, emails are on
  ``demo.example.com`` (RFC 2606 reserved, cannot receive mail) and phone numbers are
  in one fixed made-up block (+91 90000 0xxxx). The D3 outbound gate also suppresses
  every email/SMS for a demo org.

Data generation is pure (``build_plan``) so it is unit-tested without a database.
"""

from __future__ import annotations

import random
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from faker import Faker

from app.modules.appointments.models import (
    AppointmentStatus,
    AppointmentType,
    CancellationReason,
)
from app.modules.billing.invoices.models import InvoiceStatus, ServiceCategory
from app.modules.billing.payments.models import PaymentMethod, PaymentStatus
from app.modules.clinical.encounters.models import EncounterStatus, EncounterType
from app.modules.clinics.models import ClinicType
from app.modules.doctors.models import DayOfWeek, DoctorStatus
from app.modules.organizations.models import (
    MembershipStatus,
    OrganizationStatus,
    SubscriptionPlan,
)
from app.modules.patients.models import BloodGroup
from app.modules.prescriptions.models import FrequencyCode, MealRelation, PrescriptionStatus
from app.modules.users.models import UserStatus

# ── Fixed identity of the demo tenant ─────────────────────────────────────────
DEMO_ORG_ID = uuid.UUID("00000000-0000-0000-00de-000000000001")
DEMO_ORG_SLUG = "solidcare-demo-tenant"
DEMO_CLINIC_ID = uuid.UUID("00000000-0000-0000-00de-000000000010")
DEMO_EMAIL_DOMAIN = "demo.example.com"
DEMO_PHONE_PREFIX = "+9190000"  # + 5 digits → +91 90000 0xxxx, one made-up block

DEFAULT_SEED = 4193
DEFAULT_PATIENTS = 50
HISTORY_DAYS = 182
UPCOMING_DAYS = 7
PASSWORD_ENV = "DEMO_SEED_PASSWORD"

# RBAC seed roles (migration c4e8a1b2d903). Their permissions are copied onto
# demo-org roles, because permissions are resolved per org at login.
SOURCE_ROLE_IDS = {
    "admin": uuid.UUID("00000000-0000-0020-0000-000000000001"),
    "doctor": uuid.UUID("00000000-0000-0020-0000-000000000002"),
    "receptionist": uuid.UUID("00000000-0000-0020-0000-000000000003"),
}
ROLE_NAMES = {"admin": "Organization Admin", "doctor": "Doctor", "receptionist": "Receptionist"}

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://solidcare.health/demo-tenant")
_IST = ZoneInfo("Asia/Kolkata")

# (key, first name, last name, role, doctor profile or None)
STAFF = [
    ("admin", "Demo", "Admin", "admin", None),
    ("doctor1", "Asha", "Demo", "doctor",
     {"specializations": ["General Medicine"], "qualifications": ["MBBS", "MD"], "fee": 500.0, "years": 12}),
    ("doctor2", "Kabir", "Demo", "doctor",
     {"specializations": ["Paediatrics"], "qualifications": ["MBBS", "DCH"], "fee": 600.0, "years": 8}),
    ("reception", "Demo", "Reception", "receptionist", None),
]

# (complaint, impression, plan, [(medicine, dosage, frequency, days, meal)])
CONDITIONS = [
    ("Fever and body ache for 2 days", "Viral fever", "Rest, fluids, paracetamol SOS",
     [("Paracetamol 650 mg", "1 tab", FrequencyCode.TDS, 3, MealRelation.AFTER_FOOD)]),
    ("Sore throat and cough", "Acute pharyngitis", "Warm saline gargles, review in 5 days",
     [("Azithromycin 500 mg", "1 tab", FrequencyCode.OD, 3, MealRelation.BEFORE_FOOD),
      ("Cetirizine 10 mg", "1 tab", FrequencyCode.HS, 5, MealRelation.ANY_TIME)]),
    ("Routine BP check", "Essential hypertension, controlled", "Continue medication, low-salt diet",
     [("Amlodipine 5 mg", "1 tab", FrequencyCode.OD, 30, MealRelation.AFTER_FOOD)]),
    ("Follow-up for blood sugar", "Type 2 diabetes mellitus", "Diet control, HbA1c in 3 months",
     [("Metformin 500 mg", "1 tab", FrequencyCode.BD, 30, MealRelation.AFTER_FOOD)]),
    ("Acidity and heartburn", "Gastritis", "Avoid spicy food, small frequent meals",
     [("Pantoprazole 40 mg", "1 tab", FrequencyCode.OD, 14, MealRelation.EMPTY_STOMACH)]),
    ("Lower back pain", "Mechanical low back pain", "Physiotherapy, posture advice",
     [("Aceclofenac 100 mg", "1 tab", FrequencyCode.BD, 5, MealRelation.AFTER_FOOD),
      ("Thiocolchicoside 4 mg", "1 tab", FrequencyCode.BD, 5, MealRelation.AFTER_FOOD)]),
    ("Runny nose and sneezing", "Allergic rhinitis", "Avoid dust, steam inhalation",
     [("Levocetirizine 5 mg", "1 tab", FrequencyCode.HS, 7, MealRelation.ANY_TIME)]),
    ("Headache, recurrent", "Tension-type headache", "Sleep hygiene, screen breaks",
     [("Paracetamol 500 mg", "1 tab", FrequencyCode.SOS, 5, MealRelation.AFTER_FOOD)]),
]
ALLERGIES = ["Penicillin", "Sulfa drugs", "Dust", "Peanuts"]
KNOWN_CONDITIONS = ["Hypertension", "Type 2 diabetes", "Asthma", "Hypothyroidism"]
CITIES = [("Zirakpur", "Punjab", "140603"), ("Mohali", "Punjab", "160062"),
          ("Chandigarh", "Chandigarh", "160017"), ("Panchkula", "Haryana", "134109")]
SLOTS = [time(9 + (15 * i) // 60, (15 * i) % 60) for i in range(16)]  # 09:00 … 12:45


class DemoSeedRefused(RuntimeError):
    """The target database is not safe to seed (e.g. the org is not a demo org)."""


@dataclass
class SeedPlan:
    """Rows to upsert, by table name, in foreign-key order."""

    today: date
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    staff_emails: dict[str, str] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


TABLE_ORDER = [
    "organizations", "clinics", "roles", "users", "memberships", "user_roles",
    "doctors", "doctor_clinic_assignments", "doctor_schedules", "patients",
    "appointments", "encounters", "prescriptions", "prescription_items",
    "invoices", "invoice_line_items", "payments",
]


def _id(*parts: object) -> uuid.UUID:
    return uuid.uuid5(_NS, ":".join(str(p) for p in parts))


def _ascii(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower()) or "x"


def _at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=_IST)


def _hhmmss(t: time) -> str:
    return t.strftime("%H:%M:%S")


def _working_day(d: date) -> bool:
    return d.weekday() != 6  # clinic closed on Sundays


def build_plan(seed: int = DEFAULT_SEED, today: date | None = None,
               n_patients: int = DEFAULT_PATIENTS) -> SeedPlan:
    """Build every demo row in memory. Pure: same seed and today → same rows."""
    today = today or date.today()
    rng = random.Random(seed)
    fake = Faker("en_IN")
    fake.seed_instance(seed)
    plan = SeedPlan(today=today, tables={name: [] for name in TABLE_ORDER})
    t = plan.tables
    org = DEMO_ORG_ID
    clinic = DEMO_CLINIC_ID

    t["organizations"].append({
        "id": org, "name": "Solidcare Demo Clinic (sample data)", "slug": DEMO_ORG_SLUG,
        "schema_name": "solidcare_demo_tenant", "email": f"clinic@{DEMO_EMAIL_DOMAIN}",
        "phone": f"{DEMO_PHONE_PREFIX}00000", "city": "Zirakpur", "state": "Punjab",
        "country": "India", "subscription_plan": SubscriptionPlan.FREE,
        "status": OrganizationStatus.ACTIVE, "is_demo": True,
    })
    t["clinics"].append({
        "id": clinic, "organization_id": org, "name": "Solidcare Demo Clinic", "code": "DEMOT1",
        "clinic_type": ClinicType.GENERAL, "phone": f"{DEMO_PHONE_PREFIX}00000",
        "email": f"clinic@{DEMO_EMAIL_DOMAIN}", "city": "Zirakpur", "state": "Punjab",
        "pincode": "140603", "is_active": True,
    })
    for slug, name in ROLE_NAMES.items():
        t["roles"].append({
            "id": _id("role", slug), "organization_id": org, "name": name, "slug": slug,
            "description": f"{name} (demo tenant)", "is_system_role": False,
        })

    doctors: list[dict[str, Any]] = []
    for key, first, last, role, profile in STAFF:
        user_id = _id("user", key)
        email = f"{key}@{DEMO_EMAIL_DOMAIN}"
        plan.staff_emails[key] = email
        t["users"].append({
            "id": user_id, "organization_id": org, "email": email, "first_name": first,
            "last_name": last, "status": UserStatus.ACTIVE, "is_superadmin": False,
            "mfa_enabled": False, "email_verified": True, "phone_verified": False,
            "failed_login_attempts": 0,
        })
        t["memberships"].append({
            "id": _id("membership", key), "user_id": user_id, "organization_id": org,
            "status": MembershipStatus.ACTIVE, "is_default": True,
        })
        t["user_roles"].append({
            "id": _id("user_role", key), "user_id": user_id, "role_id": _id("role", role),
            "clinic_id": clinic,
        })
        if profile:
            doctor_id = _id("doctor", key)
            doctors.append({"id": doctor_id, "user_id": user_id, "fee": profile["fee"]})
            t["doctors"].append({
                "id": doctor_id, "organization_id": org, "user_id": user_id,
                "registration_number": f"DEMO-REG-{len(doctors):04d}",
                "registration_council": "Demo Medical Council",
                "qualifications": profile["qualifications"],
                "specializations": profile["specializations"],
                "years_of_experience": profile["years"], "consultation_fee": profile["fee"],
                "follow_up_fee": profile["fee"] / 2, "status": DoctorStatus.ACTIVE,
                "languages": ["English", "Hindi", "Punjabi"],
            })
            t["doctor_clinic_assignments"].append({
                "id": _id("assignment", key), "doctor_id": doctor_id, "clinic_id": clinic,
                "is_primary": True, "is_active": True,
            })
            for day in list(DayOfWeek)[:6]:  # Monday–Saturday
                t["doctor_schedules"].append({
                    "id": _id("schedule", key, day.value), "doctor_id": doctor_id,
                    "clinic_id": clinic, "day_of_week": day, "start_time": "09:00:00",
                    "end_time": "13:00:00", "slot_duration_minutes": 15,
                    "max_appointments": 16, "is_active": True,
                })

    start = today - timedelta(days=HISTORY_DAYS)
    visits: list[dict[str, Any]] = []
    for i in range(1, n_patients + 1):
        gender = rng.choice(["male", "female"])
        first = fake.first_name_male() if gender == "male" else fake.first_name_female()
        last = fake.last_name()
        city, state, pincode = rng.choice(CITIES)
        registered = start + timedelta(days=rng.randrange(0, 60))
        patient_id = _id("patient", i)
        t["patients"].append({
            "id": patient_id, "organization_id": org, "uhid": f"DEMO-PT{i:04d}",
            "first_name": first, "last_name": last,
            "date_of_birth": today - timedelta(days=rng.randint(365, 85 * 365)),
            "gender": gender, "blood_group": rng.choice(list(BloodGroup)[:8]),
            "phone": f"{DEMO_PHONE_PREFIX}{i:05d}",
            "email": f"{_ascii(first)}.{_ascii(last)}{i}@{DEMO_EMAIL_DOMAIN}",
            "address_line1": fake.street_address(), "city": city, "state": state,
            "pincode": pincode, "country": "India",
            "known_allergies": rng.sample(ALLERGIES, k=rng.choice([0, 0, 0, 1])),
            "known_conditions": rng.sample(KNOWN_CONDITIONS, k=rng.choice([0, 0, 1, 1, 2])),
            "emergency_contact_name": fake.name(),
            "emergency_contact_phone": f"{DEMO_PHONE_PREFIX}{n_patients + i:05d}",
            "emergency_contact_relation": rng.choice(["Spouse", "Parent", "Sibling", "Child"]),
            "is_active": True, "is_merged": False, "created_at": _at(registered, time(9, 0)),
        })
        doctor = rng.choice(doctors)
        day = registered
        for n in range(rng.randint(1, 5)):
            if n:
                day = day + timedelta(days=rng.randint(10, 45))
            while not _working_day(day):
                day += timedelta(days=1)
            if day >= today:
                break
            visits.append({"patient_id": patient_id, "doctor": doctor, "date": day,
                           "slot": rng.choice(SLOTS), "upcoming": False, "follow_up": n > 0})
        if rng.random() < 0.25:  # a few booked for the coming week
            day = today + timedelta(days=rng.randint(0, UPCOMING_DAYS))
            while not _working_day(day):
                day += timedelta(days=1)
            visits.append({"patient_id": patient_id, "doctor": doctor, "date": day,
                           "slot": rng.choice(SLOTS), "upcoming": True, "follow_up": False})

    visits.sort(key=lambda v: (v["date"], v["doctor"]["id"].hex, v["slot"], v["patient_id"].hex))
    tokens: Counter[tuple[date, uuid.UUID]] = Counter()
    receipts = 0
    invoices_per_year: defaultdict[int, int] = defaultdict(int)
    for k, v in enumerate(visits, start=1):
        doctor = v["doctor"]
        d, slot = v["date"], v["slot"]
        tokens[(d, doctor["id"])] += 1
        condition = rng.choice(CONDITIONS)
        if v["upcoming"]:
            status = rng.choice([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED])
        else:
            roll = rng.random()
            status = (AppointmentStatus.COMPLETED if roll < 0.82 else
                      AppointmentStatus.CANCELLED if roll < 0.92 else AppointmentStatus.NO_SHOW)
        appt_id = _id("appointment", k)
        begin = _at(d, slot)
        end = begin + timedelta(minutes=15)
        appt = {
            "id": appt_id, "organization_id": org, "clinic_id": clinic,
            "patient_id": v["patient_id"], "doctor_id": doctor["id"], "appointment_date": d,
            "start_time": _hhmmss(slot), "end_time": _hhmmss(end.time()),
            "appointment_type": (AppointmentType.FOLLOW_UP if v["follow_up"]
                                 else AppointmentType.SCHEDULED),
            "status": status, "token_number": tokens[(d, doctor["id"])],
            "chief_complaint": condition[0], "checked_in_at": None,
            "consultation_started_at": None, "consultation_ended_at": None,
            "cancellation_reason": None, "cancelled_at": None, "is_reminder_sent": False,
            "created_at": begin - timedelta(days=rng.randint(0, 5)),
        }
        t["appointments"].append(appt)
        if status == AppointmentStatus.CANCELLED:
            appt["cancellation_reason"] = CancellationReason.PATIENT_REQUEST
            appt["cancelled_at"] = begin - timedelta(hours=rng.randint(2, 30))
        if status != AppointmentStatus.COMPLETED:
            continue

        appt["checked_in_at"] = begin - timedelta(minutes=10)
        appt["consultation_started_at"] = begin
        appt["consultation_ended_at"] = end
        encounter_id = _id("encounter", k)
        t["encounters"].append({
            "id": encounter_id, "organization_id": org, "clinic_id": clinic,
            "patient_id": v["patient_id"], "doctor_id": doctor["id"], "appointment_id": appt_id,
            "encounter_type": EncounterType.OPD, "status": EncounterStatus.COMPLETED,
            "encounter_date": begin, "chief_complaint": condition[0],
            "clinical_impression": condition[1], "treatment_plan": condition[2],
            "follow_up_days": rng.choice([None, 7, 14, 30]), "completed_at": end,
            "created_at": begin,
        })
        prescription_id = _id("prescription", k)
        t["prescriptions"].append({
            "id": prescription_id, "encounter_id": encounter_id, "patient_id": v["patient_id"],
            "doctor_id": doctor["id"], "clinic_id": clinic,
            "status": PrescriptionStatus.FINALIZED, "diagnosis_summary": condition[1],
            "created_at": end,
        })
        for order, (medicine, dosage, freq, days, meal) in enumerate(condition[3]):
            t["prescription_items"].append({
                "id": _id("prescription_item", k, order), "prescription_id": prescription_id,
                "medicine_name": medicine, "dosage": dosage, "frequency": freq,
                "duration_days": days, "meal_relation": meal, "sort_order": order,
            })
        fee = doctor["fee"] / 2 if v["follow_up"] else doctor["fee"]
        paid = rng.random() < 0.88
        invoices_per_year[d.year] += 1
        invoice_id = _id("invoice", k)
        t["invoices"].append({
            "id": invoice_id, "organization_id": org, "clinic_id": clinic,
            "patient_id": v["patient_id"], "encounter_id": encounter_id,
            "invoice_number": f"DEMO-INV-{d.year}-{invoices_per_year[d.year]:05d}",
            "invoice_date": d, "due_date": d,
            "status": InvoiceStatus.PAID if paid else InvoiceStatus.ISSUED,
            "subtotal": fee, "discount_amount": 0.0, "discount_percentage": 0.0,
            "taxable_amount": fee, "total_tax": 0.0, "total_amount": fee,
            "paid_amount": fee if paid else 0.0, "outstanding_amount": 0.0 if paid else fee,
            "created_at": end,
        })
        t["invoice_line_items"].append({
            "id": _id("invoice_line", k), "invoice_id": invoice_id,
            "service_category": ServiceCategory.CONSULTATION,
            "description": "Follow-up consultation" if v["follow_up"] else "Consultation",
            "quantity": 1.0, "unit_price": fee, "discount_amount": 0.0, "tax_rate": 0.0,
            "tax_amount": 0.0, "total_amount": fee, "sort_order": 0,
        })
        if paid:
            receipts += 1
            t["payments"].append({
                "id": _id("payment", k), "organization_id": org, "clinic_id": clinic,
                "invoice_id": invoice_id, "patient_id": v["patient_id"],
                "payment_method": rng.choice([PaymentMethod.UPI, PaymentMethod.UPI,
                                              PaymentMethod.CASH, PaymentMethod.CARD]),
                "status": PaymentStatus.COMPLETED, "amount": fee, "paid_at": end,
                "receipt_number": f"DEMO-RCPT-{receipts:05d}",
            })
    return plan


def validate_plan(plan: SeedPlan) -> None:
    """Refuse a plan that would write anything outside the demo org/clinic."""
    for table, rows in plan.tables.items():
        for row in rows:
            if table == "organizations":
                if row["id"] != DEMO_ORG_ID or row.get("is_demo") is not True:
                    raise DemoSeedRefused("plan writes a non-demo organization")
            if "organization_id" in row and row["organization_id"] != DEMO_ORG_ID:
                raise DemoSeedRefused(f"{table} row outside the demo org")
            if "clinic_id" in row and row["clinic_id"] != DEMO_CLINIC_ID:
                raise DemoSeedRefused(f"{table} row outside the demo clinic")
            email = row.get("email")
            if email and not email.endswith(f"@{DEMO_EMAIL_DOMAIN}"):
                raise DemoSeedRefused(f"{table} row has a deliverable email")


def check_target_org(existing: list[tuple[uuid.UUID, str, bool]]) -> str:
    """Decide what to do given orgs matching the demo id or slug.

    Returns "create" or "refresh"; raises DemoSeedRefused when unsafe.
    """
    if not existing:
        return "create"
    for org_id, slug, is_demo in existing:
        if org_id != DEMO_ORG_ID:
            raise DemoSeedRefused(f"slug {slug!r} belongs to another organization ({org_id})")
        if not is_demo:
            raise DemoSeedRefused(
                f"organization {org_id} exists but is_demo is false; refusing to touch it"
            )
    return "refresh"


async def apply_plan(session: Any, plan: SeedPlan, password_hash: str) -> str:
    """Upsert the plan in the caller's transaction. Returns "create" or "refresh"."""
    from sqlalchemy import bindparam, func, text
    from sqlalchemy.dialects.postgresql import insert

    import app.register_models  # noqa: F401  (populates Base.metadata)
    from app.database import Base

    validate_plan(plan)
    result = await session.execute(
        text("SELECT id, slug, is_demo FROM organizations WHERE id = :id OR slug = :slug"),
        {"id": DEMO_ORG_ID, "slug": DEMO_ORG_SLUG},
    )
    action = check_target_org([tuple(r) for r in result.all()])

    source = await session.execute(
        text("SELECT role_id, permission_id FROM role_permissions "
             "WHERE role_id IN :ids AND deleted_at IS NULL").bindparams(
            bindparam("ids", expanding=True)),
        {"ids": list(SOURCE_ROLE_IDS.values())},
    )
    perms: defaultdict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for role_id, permission_id in source.all():
        perms[role_id].append(permission_id)
    missing = [slug for slug, rid in SOURCE_ROLE_IDS.items() if not perms[rid]]
    if missing:
        raise DemoSeedRefused(f"RBAC seed roles have no permissions: {missing} "
                              "(run `alembic upgrade head` first)")

    # RLS (migration b2c3d4e5f6a7) scopes patients/encounters/invoices/payments/
    # appointments to app.current_org_id; set it for this transaction only.
    await session.execute(text(f"SET LOCAL app.current_org_id = '{DEMO_ORG_ID}'"))

    tables = dict(plan.tables)
    tables["users"] = [{**u, "hashed_password": password_hash} for u in tables["users"]]
    tables["role_permissions"] = [
        {"id": _id("role_permission", slug, pid), "role_id": _id("role", slug),
         "permission_id": pid}
        for slug, rid in SOURCE_ROLE_IDS.items() for pid in sorted(perms[rid], key=str)
    ]
    order = TABLE_ORDER[:3] + ["role_permissions"] + TABLE_ORDER[3:]
    for name in order:
        rows = tables[name]
        if not rows:
            continue
        keys = sorted(rows[0])
        if any(sorted(r) != keys for r in rows):
            raise DemoSeedRefused(f"{name}: rows have different columns")
        table = Base.metadata.tables[name]
        stmt = insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in keys if k != "id"}
            | {"deleted_at": None, "updated_at": func.now()},
        )
        await session.execute(stmt)
    return action
