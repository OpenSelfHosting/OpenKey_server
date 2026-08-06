from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_service, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.rate_limit import limit_auth_endpoint
from app.schemas.auth import (
    DeleteAccountRequest,
    KeysUpdateRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    PreloginRequest,
    PreloginResponse,
    PublicKeyLookupRequest,
    PublicKeyLookupResponse,
    RefreshRequest,
    RegisterRequest,
    RekeyRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_auth_endpoint)],
)
async def register(
    body: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        return await auth.register(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/prelogin",
    response_model=PreloginResponse,
    dependencies=[Depends(limit_auth_endpoint)],
)
async def prelogin(
    body: PreloginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> PreloginResponse:
    """Return salt + KDF params so the client can derive auth_hash before login."""
    try:
        return await auth.prelogin(body)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit_auth_endpoint)],
)
async def login(
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        return await auth.login(body)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(limit_auth_endpoint)],
)
async def refresh(
    body: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        return await auth.refresh(body.refresh_token)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.revoke_refresh_token(body.refresh_token)


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    """Permanently delete the authenticated account after auth_hash verification."""
    try:
        await auth.delete_account(current_user, body)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _me_response(user: User) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        email=user.email,
        public_key=user.public_key,
        encrypted_private_key=user.encrypted_private_key,
        salt=user.salt,
        encrypted_vault_key=user.encrypted_vault_key,
        kdf_params=user.kdf_params,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    return _me_response(current_user)


@router.patch("/me/keys", response_model=MeResponse)
async def update_keys(
    body: KeysUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    current_user.public_key = body.public_key
    current_user.encrypted_private_key = body.encrypted_private_key
    current_user.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(current_user)
    return _me_response(current_user)


@router.post("/rekey", response_model=MeResponse)
async def rekey(
    body: RekeyRequest,
    current_user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> MeResponse:
    """Rotate auth_hash + wrapped vault key after a client-side master-password change."""
    try:
        user = await auth.rekey(current_user, body)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return _me_response(user)


@router.post("/lookup-public-key", response_model=PublicKeyLookupResponse)
async def lookup_public_key(
    body: PublicKeyLookupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PublicKeyLookupResponse:
    """Return another user's identity public key for client-side key wrapping.

    Only the opaque public key is exposed — never the encrypted private key.
    """
    _ = current_user
    email = body.email.lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return PublicKeyLookupResponse(
        user_id=user.id,
        email=user.email,
        public_key=user.public_key,
    )
