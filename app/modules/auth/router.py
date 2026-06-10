from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import AuthRequired, get_current_user
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
) -> TokenResponse:
    import uuid
    # In a real multi-tenant setup the org_id would come from subdomain or header.
    # For now we use a placeholder that the frontend passes as X-Org-Id header.
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")  # default org
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
