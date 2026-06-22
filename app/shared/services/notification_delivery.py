"""Notification delivery providers for SMS and email."""

from __future__ import annotations

import logging

import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import settings

logger = logging.getLogger(__name__)


def send_email_via_sendgrid(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send an email using SendGrid. Returns False when provider is not configured or call fails."""
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not configured; skipping email delivery to %s", to_email)
        return False

    mail = Mail(
        from_email=(settings.EMAIL_FROM_ADDRESS, settings.EMAIL_FROM_NAME),
        to_emails=to_email,
        subject=subject,
        plain_text_content=body_text,
        html_content=body_html,
    )

    try:
        response = SendGridAPIClient(settings.SENDGRID_API_KEY).send(mail)
        if 200 <= response.status_code < 300:
            return True
        logger.error("SendGrid rejected email to %s with status %s", to_email, response.status_code)
        return False
    except Exception:
        logger.exception("SendGrid delivery failed for %s", to_email)
        return False


def send_sms_via_msg91(phone: str, message: str) -> bool:
    """Send SMS using MSG91 API. Returns False when provider is not configured or call fails."""
    if not settings.MSG91_AUTH_KEY:
        logger.warning("MSG91_AUTH_KEY not configured; skipping SMS delivery to %s", phone)
        return False

    payload = {
        "sender": settings.MSG91_SENDER_ID,
        "route": "4",
        "country": "91",
        "sms": [
            {
                "message": message,
                "to": [phone],
            }
        ],
    }
    headers = {
        "authkey": settings.MSG91_AUTH_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post("https://api.msg91.com/api/v2/sendsms", json=payload, headers=headers, timeout=15)
        if 200 <= response.status_code < 300:
            return True
        logger.error("MSG91 rejected SMS to %s with status %s: %s", phone, response.status_code, response.text)
        return False
    except Exception:
        logger.exception("MSG91 delivery failed for %s", phone)
        return False
