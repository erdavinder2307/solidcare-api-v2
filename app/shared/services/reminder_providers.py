"""Reminder delivery providers (SE-4194).

One small interface, ``ReminderProvider``, with:
  - ``MetaWhatsAppCloudProvider``: Meta WhatsApp Cloud API, approved template message
    (Graph API ``POST /{phone-number-id}/messages``). Token and phone-number-id come
    ONLY from settings.
  - ``UnavailableProvider``: used for any channel with no provider chosen (SMS today).
  - ``FakeProvider``: in-memory, for tests.

Patient phone numbers are never logged: use ``mask_phone`` in every log line.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

META_GRAPH_BASE_URL = "https://graph.facebook.com"


@dataclass(frozen=True)
class ReminderMessage:
    """What a provider needs to send one appointment reminder."""

    to: str  # normalized digits with country code, no "+", e.g. "910000000001"
    patient_first_name: str
    clinic_name: str
    date_text: str  # e.g. "14 Nov 2026"
    time_text: str  # e.g. "10:30 AM"

    def template_parameters(self) -> list[str]:
        """Order of the WhatsApp template body variables {{1}}..{{4}}."""
        return [self.patient_first_name, self.clinic_name, self.date_text, self.time_text]

    def plain_text(self) -> str:
        return (
            f"Hello {self.patient_first_name}, this is a reminder of your appointment at "
            f"{self.clinic_name} on {self.date_text} at {self.time_text}."
        )


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class ReminderProvider(Protocol):
    channel: str  # "whatsapp" | "sms"
    name: str

    @property
    def available(self) -> bool: ...

    async def send(self, message: ReminderMessage) -> SendResult: ...


def mask_phone(phone: str | None) -> str:
    """Log-safe form of a phone number: only the last 2 digits survive."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return "<none>"
    return "*" * max(len(digits) - 2, 0) + digits[-2:]


def normalize_phone(phone: str | None, default_country_code: str = "91") -> str | None:
    """Digits-only international number (no "+"), or None when unusable.

    A 10-digit number is treated as national and gets the default country code;
    a leading trunk "0" on an 11-digit number is dropped first.
    """
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = default_country_code + digits
    if len(digits) < 11 or len(digits) > 15:
        return None
    return digits


class UnavailableProvider:
    """A channel with no provider configured. Never sends anything."""

    def __init__(self, channel: str, reason: str = "no provider configured") -> None:
        self.channel = channel
        self.name = "none"
        self._reason = reason

    @property
    def available(self) -> bool:
        return False

    async def send(self, message: ReminderMessage) -> SendResult:
        return SendResult(ok=False, error=f"{self.channel} unavailable: {self._reason}")


@dataclass
class FakeProvider:
    """Test double. Records every message it is asked to send."""

    channel: str
    name: str = "fake"
    is_available: bool = True
    fail_with: str | None = None
    sent: list[ReminderMessage] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.is_available

    async def send(self, message: ReminderMessage) -> SendResult:
        self.sent.append(message)
        if self.fail_with:
            return SendResult(ok=False, error=self.fail_with)
        return SendResult(ok=True, provider_message_id=f"{self.name}-{self.channel}-{len(self.sent)}")


class MetaWhatsAppCloudProvider:
    """Meta WhatsApp Cloud API: sends an approved template message.

    Requires REMINDER_WHATSAPP_PROVIDER=meta, WHATSAPP_CLOUD_API_TOKEN and
    WHATSAPP_CLOUD_PHONE_NUMBER_ID. The template named by
    WHATSAPP_REMINDER_TEMPLATE_NAME must be approved in WhatsApp Manager with
    four body variables: patient first name, clinic name, date, time.
    """

    channel = "whatsapp"
    name = "meta_cloud_api"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = settings.WHATSAPP_CLOUD_API_TOKEN
        self._phone_number_id = settings.WHATSAPP_CLOUD_PHONE_NUMBER_ID
        self._version = settings.WHATSAPP_CLOUD_API_VERSION
        self._template = settings.WHATSAPP_REMINDER_TEMPLATE_NAME
        self._language = settings.WHATSAPP_REMINDER_TEMPLATE_LANGUAGE
        self._transport = transport  # tests inject httpx.MockTransport; None = real network

    @property
    def available(self) -> bool:
        return bool(self._token and self._phone_number_id and self._template)

    def build_payload(self, message: ReminderMessage) -> dict:
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.to,
            "type": "template",
            "template": {
                "name": self._template,
                "language": {"code": self._language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": value} for value in message.template_parameters()
                        ],
                    }
                ],
            },
        }

    async def send(self, message: ReminderMessage) -> SendResult:
        if not self.available:
            return SendResult(ok=False, error="whatsapp unavailable: Meta Cloud API not configured")
        url = f"{META_GRAPH_BASE_URL}/{self._version}/{self._phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15) as client:
                response = await client.post(url, json=self.build_payload(message), headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp reminder to %s failed: %s", mask_phone(message.to), type(exc).__name__)
            return SendResult(ok=False, error=f"whatsapp transport error: {type(exc).__name__}")

        try:
            body = response.json()
        except ValueError:
            body = {}
        if 200 <= response.status_code < 300:
            messages = body.get("messages") or [{}]
            return SendResult(ok=True, provider_message_id=messages[0].get("id"))
        # Keep only Meta's error code/type: the free-text message can echo the recipient.
        err = body.get("error") or {}
        error = f"whatsapp http {response.status_code} code={err.get('code')} type={err.get('type')}"
        logger.warning("WhatsApp reminder to %s rejected: %s", mask_phone(message.to), error)
        return SendResult(ok=False, error=error)


def build_providers(settings: Settings) -> tuple[ReminderProvider, ReminderProvider]:
    """(whatsapp, sms) providers from settings. Anything not chosen is unavailable."""
    if settings.REMINDER_WHATSAPP_PROVIDER == "meta":
        whatsapp: ReminderProvider = MetaWhatsAppCloudProvider(settings)
    else:
        whatsapp = UnavailableProvider("whatsapp")
    # No SMS provider has been chosen yet (open decision): interface only.
    sms: ReminderProvider = UnavailableProvider("sms")
    return whatsapp, sms
