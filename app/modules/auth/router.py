from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.modules.auth.dependencies import AuthRequired
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MfaSetupConfirm,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(AuthRepository(session))


@router.post("/login", response_model=TokenResponse, summary="Login with email and password")
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> TokenResponse:
    import uuid

    org_id = uuid.UUID(x_org_id) if x_org_id else uuid.UUID("00000000-0000-0000-0000-000000000001")
    return await service.login(payload.email, payload.password, org_id)


@router.post("/mfa/verify", response_model=TokenResponse, summary="Verify MFA TOTP code")
async def verify_mfa(
    payload: MfaVerifyRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    return await service.verify_mfa(payload.mfa_token, payload.totp_code)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(
    payload: RefreshTokenRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    return await service.refresh_token(payload.refresh_token)


@router.post("/logout", status_code=204, summary="Logout and revoke refresh token")
async def logout(
    payload: LogoutRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await service.logout(payload.refresh_token)


@router.post("/mfa/setup", response_model=MfaSetupResponse, summary="Initiate MFA setup")
async def setup_mfa(
    current_user: AuthRequired,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MfaSetupResponse:
    return await service.setup_mfa(current_user.user_id)


@router.post("/mfa/confirm", summary="Confirm MFA setup with TOTP code")
async def confirm_mfa(
    payload: MfaSetupConfirm,
    current_user: AuthRequired,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict:
    await service.confirm_mfa_setup(current_user.user_id, payload.totp_code)
    return {"message": "MFA enabled successfully"}


@router.delete("/mfa", summary="Disable MFA")
async def disable_mfa(
    payload: MfaSetupConfirm,
    current_user: AuthRequired,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict:
    await service.disable_mfa(current_user.user_id, payload.totp_code)
    return {"message": "MFA disabled successfully"}


@router.post("/change-password", summary="Change password for authenticated user")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: AuthRequired,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict:
    await service.change_password(current_user.user_id, payload.current_password, payload.new_password)
    return {"message": "Password changed successfully"}


@router.post("/password-reset", summary="Request password reset token")
async def password_reset(
    payload: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> dict:
    import uuid

    org_id = uuid.UUID(x_org_id) if x_org_id else uuid.UUID("00000000-0000-0000-0000-000000000001")
    token = await service.request_password_reset(payload.email, org_id)
    response: dict = {"message": "If the email exists, a reset link has been sent"}
    if token and settings.is_development:
        response["reset_token"] = token
    return response


@router.post("/password-reset/confirm", summary="Confirm password reset")
async def password_reset_confirm(
    payload: PasswordResetConfirm,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict:
    await service.confirm_password_reset(payload.token, payload.new_password)
    return {"message": "Password reset successfully"}
