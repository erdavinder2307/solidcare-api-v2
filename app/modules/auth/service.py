import uuid
from datetime import timedelta

import redis.asyncio as aioredis

from app.config import settings
from app.core.exceptions.errors import ForbiddenError, UnauthorizedError
from app.core.security.jwt import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_token,
)
from app.core.security.mfa import (
    generate_backup_codes,
    generate_qr_code_base64,
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)
from app.core.security.password import hash_password, verify_password
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import MfaSetupResponse, TokenResponse
from app.modules.users.models import User, UserStatus

MAX_FAILED_ATTEMPTS = 5


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repo = repository
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    async def login(self, email: str, password: str, org_id: uuid.UUID) -> TokenResponse:
        user = await self.repo.get_user_by_email(email.lower(), org_id)

        if not user:
            raise UnauthorizedError("Invalid email or password")

        if user.status == UserStatus.LOCKED:
            raise ForbiddenError("Account is locked. Please contact your administrator.")

        if user.status == UserStatus.INACTIVE:
            raise ForbiddenError("Account is inactive.")

        if not verify_password(password, user.hashed_password):
            attempts = await self.repo.increment_failed_attempts(user.id)
            if attempts >= MAX_FAILED_ATTEMPTS:
                await self.repo.lock_user(user.id)
                raise ForbiddenError("Account locked due to too many failed attempts.")
            raise UnauthorizedError("Invalid email or password")

        if user.mfa_enabled:
            mfa_token = create_mfa_token(user.id)
            return TokenResponse(
                access_token="",
                refresh_token="",
                expires_in=0,
                requires_mfa=True,
                mfa_token=mfa_token,
            )

        return await self._issue_tokens(user)

    async def verify_mfa(self, mfa_token: str, totp_code: str) -> TokenResponse:
        payload = decode_token(mfa_token)
        if payload.get("token_type") != "mfa_challenge":
            raise UnauthorizedError("Invalid MFA token")

        user_id = uuid.UUID(payload["sub"])
        user = await self.repo.get_user_by_id(user_id)
        if not user or not user.mfa_secret:
            raise UnauthorizedError("MFA not configured")

        if not verify_totp(user.mfa_secret, totp_code):
            if totp_code in (user.mfa_backup_codes or []):
                codes = [c for c in user.mfa_backup_codes if c != totp_code]
                await self.repo.update_mfa_secret(user.id, user.mfa_secret, codes)
            else:
                raise UnauthorizedError("Invalid MFA code")

        return await self._issue_tokens(user)

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("token_type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")

        jti = payload.get("jti")
        is_revoked = await self._redis.get(f"revoked:refresh:{jti}")
        if is_revoked:
            raise UnauthorizedError("Token has been revoked")

        user_id = uuid.UUID(payload["sub"])
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")

        return await self._issue_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
                await self._redis.setex(f"revoked:refresh:{jti}", ttl, "1")
        except Exception:
            pass  # Logout should always succeed

    async def setup_mfa(self, user_id: uuid.UUID) -> MfaSetupResponse:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")

        secret = generate_totp_secret()
        backup_codes = generate_backup_codes()
        totp_uri = get_totp_uri(secret, user.email)
        qr_base64 = generate_qr_code_base64(totp_uri)

        await self.repo.update_mfa_secret(user_id, secret, backup_codes)

        return MfaSetupResponse(
            secret=secret,
            totp_uri=totp_uri,
            qr_code_base64=qr_base64,
            backup_codes=backup_codes,
        )

    async def confirm_mfa_setup(self, user_id: uuid.UUID, totp_code: str) -> bool:
        user = await self.repo.get_user_by_id(user_id)
        if not user or not user.mfa_secret:
            raise UnauthorizedError("MFA not configured")

        if not verify_totp(user.mfa_secret, totp_code):
            raise UnauthorizedError("Invalid TOTP code")

        await self.repo.enable_mfa(user_id)
        return True

    async def disable_mfa(self, user_id: uuid.UUID, totp_code: str) -> bool:
        user = await self.repo.get_user_by_id(user_id)
        if not user or not user.mfa_secret:
            raise UnauthorizedError("MFA not configured")

        if not verify_totp(user.mfa_secret, totp_code):
            raise UnauthorizedError("Invalid TOTP code")

        await self.repo.disable_mfa(user_id)
        return True

    async def _issue_tokens(self, user: User) -> TokenResponse:
        permissions = await self.repo.get_user_permissions(user.id)
        roles = await self.repo.get_user_roles(user.id)

        access_token = create_access_token(
            subject=user.email,
            user_id=user.id,
            org_id=user.organization_id,
            clinic_ids=[],
            permissions=permissions,
            roles=roles,
        )
        refresh_token, jti = create_refresh_token(user.id)
        ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await self._redis.setex(f"refresh:{jti}", ttl, str(user.id))
        await self.repo.update_last_login(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
