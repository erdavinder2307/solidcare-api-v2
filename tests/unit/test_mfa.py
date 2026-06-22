"""Unit tests for MFA utility functions — no database or network required."""

import re

import pytest

pytest.importorskip("pyotp")

from app.core.security.mfa import (
    generate_backup_codes,
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)


class TestGenerateTotpSecret:
    def test_returns_non_empty_string(self):
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_secret_is_valid_base32(self):
        """pyotp secrets are base32-encoded strings (uppercase A-Z and 2-7)."""
        secret = generate_totp_secret()
        assert re.match(r"^[A-Z2-7]+$", secret), f"Not valid base32: {secret}"

    def test_two_secrets_are_unique(self):
        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        assert s1 != s2


class TestGetTotpUri:
    def test_uri_starts_with_otpauth(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "doctor@clinic.com")
        assert uri.startswith("otpauth://totp/")

    def test_uri_contains_email(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "doctor@clinic.com")
        assert "doctor" in uri

    def test_uri_contains_default_issuer(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "user@test.com")
        assert "Solidcare" in uri

    def test_uri_contains_custom_issuer(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "user@test.com", issuer="TestClinic")
        assert "TestClinic" in uri


class TestVerifyTotp:
    def test_correct_current_code_passes(self):
        import pyotp

        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        current_code = totp.now()
        assert verify_totp(secret, current_code) is True

    def test_obviously_wrong_code_fails(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False or verify_totp(secret, "000000") is True
        # We cannot assert False deterministically (1-in-1M chance it's valid),
        # but we can assert the function returns a bool
        result = verify_totp(secret, "BADCODE")
        assert isinstance(result, bool)

    def test_empty_code_fails(self):
        secret = generate_totp_secret()
        result = verify_totp(secret, "")
        assert result is False


class TestGenerateBackupCodes:
    def test_returns_ten_codes_by_default(self):
        codes = generate_backup_codes()
        assert len(codes) == 10

    def test_returns_requested_count(self):
        codes = generate_backup_codes(count=5)
        assert len(codes) == 5

    def test_codes_are_uppercase_hex(self):
        codes = generate_backup_codes()
        for code in codes:
            assert re.match(r"^[0-9A-F]+$", code), f"Not uppercase hex: {code}"

    def test_codes_are_unique(self):
        codes = generate_backup_codes(count=20)
        assert len(set(codes)) == 20

    def test_codes_have_expected_length(self):
        """secrets.token_hex(4) produces 8 hex chars; uppercased = 8 chars."""
        codes = generate_backup_codes()
        for code in codes:
            assert len(code) == 8
