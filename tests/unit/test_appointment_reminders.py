"""Appointment reminders (SE-4194). Fake providers and an in-memory repository only:
no database, no network. Phone numbers are obviously fake (+910000000001 style)."""

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.config import Settings
from app.modules.notifications.reminders import (
    DeliveryOutcome,
    PostgresReminderRepository,
    ReminderCandidate,
    run_appointment_reminders,
    select_due,
)
from app.shared.services.reminder_providers import (
    FakeProvider,
    MetaWhatsAppCloudProvider,
    ReminderMessage,
    UnavailableProvider,
    build_providers,
    mask_phone,
    normalize_phone,
)

IST = ZoneInfo("Asia/Kolkata")
ORG = uuid.UUID("00000000-0000-0000-0000-00000000a001")
FAKE_PHONE = "+91 00000 00001"
FAKE_PHONE_NORMALIZED = "910000000001"
# 2026-11-12 10:00 IST
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=IST).astimezone(timezone.utc)


def make_settings(**overrides) -> Settings:
    values = {"REMINDERS_ENABLED": True, "REMINDER_LEAD_HOURS": 24}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def candidate(hours_from_now: float, *, status="SCHEDULED", phone=FAKE_PHONE, tz=None, appt_id=None):
    start = NOW.astimezone(IST) + timedelta(hours=hours_from_now)
    return ReminderCandidate(
        appointment_id=appt_id or uuid.uuid4(),
        organization_id=ORG,
        appointment_date=start.date(),
        start_time=start.strftime("%H:%M:%S"),
        status=status,
        patient_first_name="Test",
        patient_phone=phone,
        clinic_name="Demo Clinic",
        clinic_timezone=tz,
    )


class InMemoryRepo:
    """Mirrors PostgresReminderRepository: fetch excludes already-claimed rows,
    claim is insert-or-nothing on (appointment_id, kind)."""

    def __init__(self, candidates, steal_claims=False):
        self.candidates = list(candidates)
        self.rows: dict[tuple[uuid.UUID, str], dict] = {}
        self.steal_claims = steal_claims  # simulate another worker winning every claim

    async def list_org_ids(self):
        return [ORG]

    async def fetch_candidates(self, org_id, now, hours_before, kind):
        return [c for c in self.candidates if c.organization_id == org_id and (c.appointment_id, kind) not in self.rows]

    async def claim(self, org_id, appointment_id, kind):
        key = (appointment_id, kind)
        if self.steal_claims and key not in self.rows:
            self.rows[key] = {"id": uuid.uuid4(), "status": "pending", "owner": "other-worker"}
        if key in self.rows:
            return None
        rid = uuid.uuid4()
        self.rows[key] = {"id": rid, "status": "pending"}
        return rid

    async def finish(self, org_id, reminder_id, appointment_id, outcome: DeliveryOutcome):
        for row in self.rows.values():
            if row["id"] == reminder_id:
                row.update(status=outcome.status, channel=outcome.channel,
                           provider_message_id=outcome.provider_message_id, error=outcome.error,
                           sent_at=outcome.sent_at)
                return
        raise AssertionError("finish() for an unclaimed reminder")

    def row(self, appointment_id, kind="24h"):
        return self.rows[(appointment_id, kind)]


class ExplodingRepo:
    def __getattr__(self, name):
        raise AssertionError(f"repository must not be touched, got {name}")


async def run(repo, whatsapp, sms, hours=24, **settings_overrides):
    return await run_appointment_reminders(
        hours, settings=make_settings(**settings_overrides), repo=repo, providers=(whatsapp, sms), now=NOW
    )


# ── dispatch ─────────────────────────────────────────────────────────────────


async def test_sends_via_whatsapp_and_records_result():
    c = candidate(5)
    repo, wa, sms = InMemoryRepo([c]), FakeProvider("whatsapp"), FakeProvider("sms")

    result = await run(repo, wa, sms)

    assert result["sent_whatsapp"] == 1 and result["sent_sms"] == 0
    assert len(wa.sent) == 1 and sms.sent == []
    msg = wa.sent[0]
    assert msg.to == FAKE_PHONE_NORMALIZED
    assert msg.clinic_name == "Demo Clinic" and msg.date_text == "12 Nov 2026" and msg.time_text == "3:00 PM"
    row = repo.row(c.appointment_id)
    assert row["status"] == "sent" and row["channel"] == "whatsapp"
    assert row["provider_message_id"] == "fake-whatsapp-1" and row["sent_at"] == NOW


async def test_falls_back_to_sms_when_whatsapp_fails():
    c = candidate(5)
    repo = InMemoryRepo([c])
    wa, sms = FakeProvider("whatsapp", fail_with="template not approved"), FakeProvider("sms")

    result = await run(repo, wa, sms)

    assert result["sent_sms"] == 1 and result["sent_whatsapp"] == 0
    assert len(wa.sent) == 1 and len(sms.sent) == 1
    row = repo.row(c.appointment_id)
    assert row["status"] == "sent" and row["channel"] == "sms"
    assert "whatsapp: template not approved" in row["error"]


async def test_falls_back_to_sms_when_whatsapp_unavailable():
    c = candidate(5)
    repo, sms = InMemoryRepo([c]), FakeProvider("sms")

    result = await run(repo, UnavailableProvider("whatsapp"), sms)

    assert result["sent_sms"] == 1
    assert repo.row(c.appointment_id)["channel"] == "sms"


async def test_both_channels_fail_records_failure_and_is_not_retried():
    c = candidate(5)
    repo = InMemoryRepo([c])
    wa, sms = FakeProvider("whatsapp", fail_with="boom"), FakeProvider("sms", fail_with="down")

    first = await run(repo, wa, sms)
    second = await run(repo, wa, sms)

    assert first["failed"] == 1 and second["failed"] == 0 and second["due"] == 0
    row = repo.row(c.appointment_id)
    assert row["status"] == "failed" and row["channel"] is None
    assert "whatsapp: boom" in row["error"] and "sms: down" in row["error"]
    assert len(wa.sent) == 1 and len(sms.sent) == 1


async def test_provider_exception_does_not_stop_the_batch():
    class Raising(FakeProvider):
        async def send(self, message):
            raise RuntimeError("bug")

    c = candidate(5)
    repo, sms = InMemoryRepo([c]), FakeProvider("sms")
    result = await run(repo, Raising("whatsapp"), sms)
    assert result["sent_sms"] == 1


# ── no duplicates ────────────────────────────────────────────────────────────


async def test_second_run_sends_nothing():
    cs = [candidate(3), candidate(20)]
    repo, wa, sms = InMemoryRepo(cs), FakeProvider("whatsapp"), FakeProvider("sms")

    first = await run(repo, wa, sms)
    second = await run(repo, wa, sms)

    assert first["sent_whatsapp"] == 2
    assert second["sent_whatsapp"] == 0 and second["due"] == 0
    assert len(wa.sent) == 2


async def test_lost_claim_sends_nothing():
    """Another worker (or a Celery retry) claimed the row between fetch and claim."""
    repo = InMemoryRepo([candidate(5)], steal_claims=True)
    wa, sms = FakeProvider("whatsapp"), FakeProvider("sms")

    result = await run(repo, wa, sms)

    assert result["skipped_already_claimed"] == 1
    assert wa.sent == [] and sms.sent == []


async def test_24h_and_2h_reminders_are_separate_kinds():
    c = candidate(1)
    repo, wa, sms = InMemoryRepo([c]), FakeProvider("whatsapp"), FakeProvider("sms")

    await run(repo, wa, sms, hours=24)
    await run(repo, wa, sms, hours=2)
    await run(repo, wa, sms, hours=2)

    assert len(wa.sent) == 2
    assert repo.row(c.appointment_id, "24h")["status"] == "sent"
    assert repo.row(c.appointment_id, "2h")["status"] == "sent"


# ── gates ────────────────────────────────────────────────────────────────────


async def test_disabled_setting_sends_nothing_and_reads_nothing():
    wa, sms = FakeProvider("whatsapp"), FakeProvider("sms")
    result = await run_appointment_reminders(
        24, settings=make_settings(REMINDERS_ENABLED=False), repo=ExplodingRepo(),
        providers=(wa, sms), now=NOW,
    )
    assert result["status"] == "disabled"
    assert wa.sent == [] and sms.sent == []


def test_reminders_are_off_by_default():
    s = Settings(_env_file=None)
    assert s.REMINDERS_ENABLED is False
    assert s.REMINDER_WHATSAPP_PROVIDER == "none" and s.REMINDER_SMS_PROVIDER == "none"
    wa, sms = build_providers(s)
    assert not wa.available and not sms.available


async def test_enabled_without_any_provider_sends_nothing():
    result = await run(ExplodingRepo(), UnavailableProvider("whatsapp"), UnavailableProvider("sms"))
    assert result["status"] == "no_provider"


def test_celery_task_is_a_noop_with_default_settings():
    from app.core.background.tasks.notification_tasks import send_appointment_reminders

    result = send_appointment_reminders.run(hours_before=24)
    assert result["status"] == "disabled"


async def test_patient_without_phone_is_skipped_and_not_claimed():
    no_phone, bad_phone = candidate(5, phone=""), candidate(6, phone="12345")
    repo, wa, sms = InMemoryRepo([no_phone, bad_phone]), FakeProvider("whatsapp"), FakeProvider("sms")

    result = await run(repo, wa, sms)

    assert result["skipped_no_phone"] == 2
    assert wa.sent == [] and repo.rows == {}


# ── lead-time selection ──────────────────────────────────────────────────────


async def test_lead_time_selection():
    soon, later, too_far, past = candidate(1), candidate(23.5), candidate(25), candidate(-1)
    cancelled, completed = candidate(3, status="CANCELLED"), candidate(4, status="COMPLETED")
    no_show, confirmed = candidate(4, status="NO_SHOW"), candidate(6, status="CONFIRMED")
    cs = [soon, later, too_far, past, cancelled, completed, no_show, confirmed]

    due_24 = {c.appointment_id for c, _ in select_due(cs, NOW, 24, "Asia/Kolkata")}
    due_2 = {c.appointment_id for c, _ in select_due(cs, NOW, 2, "Asia/Kolkata")}

    assert due_24 == {soon.appointment_id, later.appointment_id, confirmed.appointment_id}
    assert due_2 == {soon.appointment_id}


async def test_lead_time_defaults_to_setting():
    near, mid = candidate(3), candidate(10)
    repo, wa, sms = InMemoryRepo([near, mid]), FakeProvider("whatsapp"), FakeProvider("sms")

    result = await run_appointment_reminders(
        None, settings=make_settings(REMINDER_LEAD_HOURS=6), repo=repo, providers=(wa, sms), now=NOW
    )

    assert result["hours_before"] == 6 and result["kind"] == "6h"
    assert [m.to for m in wa.sent] == [FAKE_PHONE_NORMALIZED] and result["sent_whatsapp"] == 1


def test_clinic_timezone_is_respected():
    # 18:00 local in London is 23:30 IST on 12 Nov, i.e. 13.5h from NOW: inside 24h, outside 12h.
    c = ReminderCandidate(
        appointment_id=uuid.uuid4(), organization_id=ORG, appointment_date=date(2026, 11, 12),
        start_time="18:00", status="SCHEDULED", patient_first_name="Test",
        patient_phone=FAKE_PHONE, clinic_name="Demo", clinic_timezone="Europe/London",
    )
    assert len(select_due([c], NOW, 24, "Asia/Kolkata")) == 1
    assert select_due([c], NOW, 12, "Asia/Kolkata") == []


def test_unparseable_start_time_is_skipped():
    c = candidate(3)
    bad = ReminderCandidate(**{**c.__dict__, "start_time": "soon"})
    assert select_due([bad], NOW, 24, "Asia/Kolkata") == []


# ── phone helpers / logging ──────────────────────────────────────────────────


def test_phone_helpers():
    assert normalize_phone("+91 00000 00001") == "910000000001"
    assert normalize_phone("0000000001") == "910000000001"
    assert normalize_phone("00000000001") == "910000000001"
    assert normalize_phone("") is None and normalize_phone(None) is None and normalize_phone("123") is None
    assert mask_phone("+910000000001") == "**********01"
    assert mask_phone(None) == "<none>"


async def test_failed_send_log_masks_phone(caplog):
    repo = InMemoryRepo([candidate(5)])
    wa, sms = FakeProvider("whatsapp", fail_with="x"), FakeProvider("sms", fail_with="y")
    with caplog.at_level(logging.DEBUG):
        await run(repo, wa, sms)
    assert caplog.records
    assert FAKE_PHONE_NORMALIZED not in caplog.text and "0000000001" not in caplog.text


# ── Meta WhatsApp Cloud API adapter (mock transport, never the network) ──────


def meta_settings(**overrides):
    values = {
        "REMINDER_WHATSAPP_PROVIDER": "meta",
        "WHATSAPP_CLOUD_API_TOKEN": "test-token-not-real",
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID": "100000000000001",
        "WHATSAPP_REMINDER_TEMPLATE_NAME": "appointment_reminder",
    }
    values.update(overrides)
    return make_settings(**values)


MESSAGE = ReminderMessage(
    to=FAKE_PHONE_NORMALIZED, patient_first_name="Test", clinic_name="Demo Clinic",
    date_text="12 Nov 2026", time_text="3:00 PM",
)


async def test_meta_adapter_sends_template_message():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.TEST"}]})

    provider = MetaWhatsAppCloudProvider(meta_settings(), transport=httpx.MockTransport(handler))
    result = await provider.send(MESSAGE)

    assert result.ok and result.provider_message_id == "wamid.TEST"
    assert seen["url"] == "https://graph.facebook.com/v21.0/100000000000001/messages"
    assert seen["auth"] == "Bearer test-token-not-real"
    body = seen["body"]
    assert body["messaging_product"] == "whatsapp" and body["type"] == "template"
    assert body["to"] == FAKE_PHONE_NORMALIZED
    assert body["template"]["name"] == "appointment_reminder"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params == ["Test", "Demo Clinic", "12 Nov 2026", "3:00 PM"]


async def test_meta_adapter_error_keeps_code_only_and_masks_phone(caplog):
    def handler(request):
        return httpx.Response(400, json={"error": {"message": f"bad recipient {FAKE_PHONE_NORMALIZED}",
                                                   "type": "OAuthException", "code": 131026}})

    provider = MetaWhatsAppCloudProvider(meta_settings(), transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.WARNING):
        result = await provider.send(MESSAGE)

    assert not result.ok and "code=131026" in result.error
    assert FAKE_PHONE_NORMALIZED not in result.error and FAKE_PHONE_NORMALIZED not in caplog.text


async def test_meta_adapter_transport_error():
    def handler(request):
        raise httpx.ConnectError("no network in tests")

    provider = MetaWhatsAppCloudProvider(meta_settings(), transport=httpx.MockTransport(handler))
    result = await provider.send(MESSAGE)
    assert not result.ok and "ConnectError" in result.error


def test_meta_adapter_unavailable_without_credentials():
    assert not MetaWhatsAppCloudProvider(meta_settings(WHATSAPP_CLOUD_API_TOKEN="")).available
    assert not MetaWhatsAppCloudProvider(meta_settings(WHATSAPP_CLOUD_PHONE_NUMBER_ID="")).available
    wa, sms = build_providers(meta_settings())
    assert isinstance(wa, MetaWhatsAppCloudProvider) and wa.available
    assert not sms.available


# ── Postgres repository SQL shape (mocked session, nothing executed) ─────────


class RecordingSession:
    def __init__(self, log, returning):
        self.log, self.returning = log, returning

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self

    async def execute(self, stmt, params=None):
        self.log.append((str(stmt), params))

        class Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        return Result(self.returning)


@pytest.mark.parametrize("returning,expected_claimed", [((uuid.uuid4(),), True), (None, False)])
async def test_postgres_claim_sets_org_context_and_uses_on_conflict(returning, expected_claimed):
    log = []
    repo = PostgresReminderRepository(lambda: RecordingSession(log, returning))

    claimed = await repo.claim(ORG, uuid.uuid4(), "24h")

    assert (claimed is not None) is expected_claimed
    assert log[0][0] == f"SET LOCAL app.current_org_id = '{ORG}'"
    assert "INSERT INTO appointment_reminders" in log[1][0]
    assert "ON CONFLICT (appointment_id, kind) DO NOTHING" in log[1][0]


async def test_postgres_fetch_filters_status_deleted_and_existing_reminders():
    log = []

    class Rows(RecordingSession):
        async def execute(self, stmt, params=None):
            self.log.append((str(stmt), params))
            return []

    repo = PostgresReminderRepository(lambda: Rows(log, None))
    await repo.fetch_candidates(ORG, NOW, 24, "24h")

    assert log[0][0].startswith("SET LOCAL app.current_org_id")
    sql = log[1][0]
    assert "a.status::text IN ('SCHEDULED', 'CONFIRMED')" in sql
    assert "a.deleted_at IS NULL" in sql and "p.deleted_at IS NULL" in sql
    assert "NOT EXISTS" in sql and "r.kind = :kind" in sql
