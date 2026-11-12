"""Appointment reminders (SE-4194).

Flow, per run (one Celery beat entry per lead time, e.g. 24h and 2h):
  1. If REMINDERS_ENABLED is false, or no channel has a provider, stop: nothing is
     read and nothing is sent.
  2. For each active organization, inside that org's RLS context
     (``SET LOCAL app.current_org_id``), load SCHEDULED/CONFIRMED appointments of
     live patients that have no reminder row of this kind yet.
  3. Keep the ones that start within (now, now + lead time] in the clinic's time zone.
  4. Per appointment: skip when the patient has no usable phone; otherwise CLAIM by
     inserting the appointment_reminders row (UNIQUE appointment_id + kind) and
     committing BEFORE any provider call. A lost claim (second run, concurrent
     worker, Celery retry) means skip. Then WhatsApp, then SMS as fallback, and the
     outcome is written to the claimed row.

Delivery is at-most-once: a FAILED or stuck PENDING row is never retried
automatically, because a provider may have delivered even when it reported an error.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from app.config import Settings
from app.modules.notifications.models import ReminderStatus
from app.shared.services.reminder_providers import (
    ReminderMessage,
    ReminderProvider,
    build_providers,
    mask_phone,
    normalize_phone,
)

logger = logging.getLogger(__name__)

# DB enum labels (SQLAlchemy stores Enum member NAMES).
ELIGIBLE_STATUSES = ("SCHEDULED", "CONFIRMED")
ACTIVE_ORG_STATUSES = ("ACTIVE", "TRIAL")
MAX_ERROR_LEN = 1000


@dataclass(frozen=True)
class ReminderCandidate:
    appointment_id: uuid.UUID
    organization_id: uuid.UUID
    appointment_date: date
    start_time: str  # "HH:MM[:SS]", clinic local time
    status: str  # DB enum label, e.g. "SCHEDULED"
    patient_first_name: str
    patient_phone: str | None
    clinic_name: str
    clinic_timezone: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str  # ReminderStatus value
    channel: str | None
    provider_message_id: str | None
    error: str | None
    sent_at: datetime | None


class ReminderRepository(Protocol):
    async def list_org_ids(self) -> list[uuid.UUID]: ...

    async def fetch_candidates(
        self, org_id: uuid.UUID, now: datetime, hours_before: int, kind: str
    ) -> list[ReminderCandidate]: ...

    async def claim(self, org_id: uuid.UUID, appointment_id: uuid.UUID, kind: str) -> uuid.UUID | None:
        """Insert the reminder row; return its id, or None if it already exists."""
        ...

    async def finish(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, appointment_id: uuid.UUID, outcome: DeliveryOutcome
    ) -> None: ...


def reminder_kind(hours_before: int) -> str:
    return f"{hours_before}h"


def appointment_start(candidate: ReminderCandidate, default_tz: str) -> datetime | None:
    """Aware start datetime in the clinic's zone, or None if the stored time is unusable."""
    try:
        tz = ZoneInfo(candidate.clinic_timezone or default_tz)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(default_tz)
    try:
        start = time.fromisoformat(candidate.start_time.strip())
    except (AttributeError, ValueError):
        return None
    return datetime.combine(candidate.appointment_date, start, tzinfo=tz)


def select_due(
    candidates: list[ReminderCandidate], now: datetime, hours_before: int, default_tz: str
) -> list[tuple[ReminderCandidate, datetime]]:
    """Appointments that start in (now, now + hours_before] and are still bookable."""
    window_end = now + timedelta(hours=hours_before)
    due = []
    for c in candidates:
        if c.status not in ELIGIBLE_STATUSES:
            continue
        start = appointment_start(c, default_tz)
        if start is None or not (now < start <= window_end):
            continue
        due.append((c, start))
    return due


def build_message(candidate: ReminderCandidate, start: datetime, phone: str) -> ReminderMessage:
    return ReminderMessage(
        to=phone,
        patient_first_name=candidate.patient_first_name or "there",
        clinic_name=candidate.clinic_name,
        date_text=f"{start.day} {start:%b %Y}",
        time_text=start.strftime("%I:%M %p").lstrip("0"),
    )


async def deliver(
    message: ReminderMessage, whatsapp: ReminderProvider, sms: ReminderProvider, now: datetime
) -> DeliveryOutcome:
    """WhatsApp first; SMS when WhatsApp fails or is unavailable."""
    errors: list[str] = []
    for provider in (whatsapp, sms):
        if not provider.available:
            errors.append(f"{provider.channel}: unavailable")
            continue
        try:
            result = await provider.send(message)
        except Exception as exc:  # a provider bug must not stop the batch
            logger.exception("Reminder provider %s raised", provider.name)
            errors.append(f"{provider.channel}: {type(exc).__name__}")
            continue
        if result.ok:
            return DeliveryOutcome(
                status=ReminderStatus.SENT.value,
                channel=provider.channel,
                provider_message_id=result.provider_message_id,
                error="; ".join(errors) or None,
                sent_at=now,
            )
        errors.append(f"{provider.channel}: {result.error}")
    return DeliveryOutcome(
        status=ReminderStatus.FAILED.value,
        channel=None,
        provider_message_id=None,
        error="; ".join(errors)[:MAX_ERROR_LEN],
        sent_at=None,
    )


async def run_appointment_reminders(
    hours_before: int | None = None,
    *,
    settings: Settings,
    repo: ReminderRepository | None = None,
    providers: tuple[ReminderProvider, ReminderProvider] | None = None,
    now: datetime | None = None,
) -> dict:
    hours = hours_before if hours_before is not None else settings.REMINDER_LEAD_HOURS
    kind = reminder_kind(hours)
    summary: dict = {"status": "ok", "hours_before": hours, "kind": kind}

    if not settings.REMINDERS_ENABLED:
        logger.info("Appointment reminders disabled (REMINDERS_ENABLED=false); nothing sent")
        return {**summary, "status": "disabled"}

    whatsapp, sms = providers or build_providers(settings)
    if not (whatsapp.available or sms.available):
        logger.warning("Appointment reminders enabled but no provider is available; nothing sent")
        return {**summary, "status": "no_provider"}

    now = now or datetime.now(timezone.utc)
    owns_repo = repo is None
    if repo is None:
        repo = PostgresReminderRepository.from_settings(settings)

    counts = dict.fromkeys(
        ["due", "sent_whatsapp", "sent_sms", "failed", "skipped_no_phone", "skipped_already_claimed", "org_errors"],
        0,
    )
    try:
        for org_id in await repo.list_org_ids():
            try:
                candidates = await repo.fetch_candidates(org_id, now, hours, kind)
                for candidate, start in select_due(candidates, now, hours, settings.REMINDER_TIMEZONE):
                    counts["due"] += 1
                    phone = normalize_phone(candidate.patient_phone, settings.REMINDER_DEFAULT_COUNTRY_CODE)
                    if phone is None:
                        counts["skipped_no_phone"] += 1
                        continue
                    reminder_id = await repo.claim(org_id, candidate.appointment_id, kind)
                    if reminder_id is None:
                        counts["skipped_already_claimed"] += 1
                        continue
                    outcome = await deliver(build_message(candidate, start, phone), whatsapp, sms, now)
                    await repo.finish(org_id, reminder_id, candidate.appointment_id, outcome)
                    if outcome.status == ReminderStatus.SENT.value:
                        counts[f"sent_{outcome.channel}"] += 1
                    else:
                        counts["failed"] += 1
                        logger.warning(
                            "Reminder %s for appointment %s to %s failed: %s",
                            kind, candidate.appointment_id, mask_phone(phone), outcome.error,
                        )
            except Exception:
                counts["org_errors"] += 1
                logger.exception("Appointment reminders failed for org %s", org_id)
    finally:
        if owns_repo:
            await repo.close()

    logger.info("Appointment reminders %s done: %s", kind, counts)
    return {**summary, **counts}


class PostgresReminderRepository:
    """Raw SQL so the Celery worker needs no ORM mapper registry. Every transaction
    sets ``app.current_org_id`` first, because appointments, patients and
    appointment_reminders have FORCE ROW LEVEL SECURITY."""

    def __init__(self, session_factory, engine=None) -> None:
        self._session_factory = session_factory
        self._engine = engine

    @classmethod
    def from_settings(cls, settings: Settings) -> "PostgresReminderRepository":
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        # NullPool: each Celery run calls asyncio.run(), so pooled asyncpg
        # connections must not outlive the event loop that created them.
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        return cls(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    @staticmethod
    async def _set_org(session, org_id: uuid.UUID) -> None:
        # org_id is a uuid.UUID, so its str() cannot inject SQL; SET takes no bind params.
        await session.execute(text(f"SET LOCAL app.current_org_id = '{uuid.UUID(str(org_id))}'"))

    async def list_org_ids(self) -> list[uuid.UUID]:
        async with self._session_factory() as session, session.begin():
            rows = await session.execute(_ORGS_SQL)
            return [row[0] for row in rows]

    async def fetch_candidates(
        self, org_id: uuid.UUID, now: datetime, hours_before: int, kind: str
    ) -> list[ReminderCandidate]:
        # Coarse date range with a day of slack each side for time zones;
        # select_due() applies the exact window.
        date_from = (now - timedelta(days=1)).date()
        date_to = (now + timedelta(hours=hours_before, days=1)).date()
        async with self._session_factory() as session, session.begin():
            await self._set_org(session, org_id)
            rows = await session.execute(
                _CANDIDATES_SQL,
                {"org_id": org_id, "date_from": date_from, "date_to": date_to, "kind": kind},
            )
            return [
                ReminderCandidate(
                    appointment_id=r.id,
                    organization_id=r.organization_id,
                    appointment_date=r.appointment_date,
                    start_time=r.start_time,
                    status=r.status,
                    patient_first_name=r.first_name,
                    patient_phone=r.phone,
                    clinic_name=r.clinic_name,
                    clinic_timezone=r.clinic_timezone,
                )
                for r in rows
            ]

    async def claim(self, org_id: uuid.UUID, appointment_id: uuid.UUID, kind: str) -> uuid.UUID | None:
        async with self._session_factory() as session, session.begin():
            await self._set_org(session, org_id)
            row = await session.execute(
                _CLAIM_SQL,
                {"id": uuid.uuid4(), "org_id": org_id, "appointment_id": appointment_id, "kind": kind,
                 "status": ReminderStatus.PENDING.value},
            )
            claimed = row.first()
            return claimed[0] if claimed else None
        # committed on leaving the block: the claim is visible before any send

    async def finish(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, appointment_id: uuid.UUID, outcome: DeliveryOutcome
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await self._set_org(session, org_id)
            await session.execute(
                _FINISH_SQL,
                {"id": reminder_id, "status": outcome.status, "channel": outcome.channel,
                 "provider_message_id": outcome.provider_message_id, "error": outcome.error,
                 "sent_at": outcome.sent_at},
            )
            if outcome.status == ReminderStatus.SENT.value:
                await session.execute(
                    text(
                        "UPDATE appointments SET is_reminder_sent = true, reminder_sent_at = :sent_at "
                        "WHERE id = :appointment_id"
                    ),
                    {"sent_at": outcome.sent_at, "appointment_id": appointment_id},
                )


_ORGS_SQL = text(
    "SELECT id FROM organizations WHERE deleted_at IS NULL "
    f"AND status::text IN ({', '.join(repr(x) for x in ACTIVE_ORG_STATUSES)})"
)

_CANDIDATES_SQL = text(
    """
    SELECT a.id, a.organization_id, a.appointment_date, a.start_time, a.status::text AS status,
           p.first_name, p.phone, c.name AS clinic_name, c.settings->>'timezone' AS clinic_timezone
    FROM appointments a
    JOIN patients p ON p.id = a.patient_id
    JOIN clinics c ON c.id = a.clinic_id
    WHERE a.organization_id = :org_id
      AND a.deleted_at IS NULL
      AND p.deleted_at IS NULL
      AND a.status::text IN ({eligible})
      AND a.appointment_date BETWEEN :date_from AND :date_to
      AND NOT EXISTS (
          SELECT 1 FROM appointment_reminders r
          WHERE r.appointment_id = a.id AND r.kind = :kind
      )
    """.format(eligible=", ".join(repr(x) for x in ELIGIBLE_STATUSES))
)

_CLAIM_SQL = text(
    """
    INSERT INTO appointment_reminders (id, organization_id, appointment_id, kind, status, created_at, updated_at)
    VALUES (:id, :org_id, :appointment_id, :kind, :status, now(), now())
    ON CONFLICT (appointment_id, kind) DO NOTHING
    RETURNING id
    """
)

_FINISH_SQL = text(
    """
    UPDATE appointment_reminders
    SET status = :status, channel = :channel, provider_message_id = :provider_message_id,
        error = :error, sent_at = :sent_at, updated_at = now()
    WHERE id = :id
    """
)
