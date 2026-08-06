import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.org import OrgMember
from app.models.refresh_token import RefreshToken
from app.models.share import Share
from app.models.user import User
from app.schemas.auth import (
    DeleteAccountRequest,
    LoginRequest,
    PreloginRequest,
    PreloginResponse,
    RegisterRequest,
    RekeyRequest,
    TokenResponse,
)


def _normalize_auth_hash(value: str) -> str:
    """Strip base64url padding so app (legacy padded) and extension match."""
    return value.strip().rstrip("=")


def verify_auth_hash(stored: str, provided: str) -> bool:
    """Constant-time comparison of client-derived auth hashes."""
    try:
        return secrets.compare_digest(
            _normalize_auth_hash(stored).encode("utf-8"),
            _normalize_auth_hash(provided).encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def _hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: UUID,
    settings: Settings | None = None,
) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    cfg = settings or get_settings()
    expires_in = cfg.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    expire = now + timedelta(seconds=expires_in)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
        "type": "access",
    }
    token = jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: Settings | None = None) -> UUID:
    cfg = settings or get_settings()
    payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    if payload.get("type", "access") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    sub = payload.get("sub")
    if not sub:
        raise jwt.InvalidTokenError("Token missing subject")
    return UUID(str(sub))


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token, expires_in = create_access_token(user.id, self.settings)
        raw_refresh = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(
            days=self.settings.refresh_token_expire_days
        )
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=_hash_refresh_token(raw_refresh),
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            user_id=user.id,
            expires_in=expires_in,
        )

    async def register(self, data: RegisterRequest) -> TokenResponse:
        existing = await self.session.scalar(
            select(User).where(User.email == data.email.lower())
        )
        if existing is not None:
            raise ValueError("Email already registered")

        user = User(
            email=data.email.lower(),
            auth_hash=data.auth_hash,
            encrypted_vault_key=data.encrypted_vault_key,
            kdf_params=data.kdf_params,
            salt=data.salt,
            public_key=data.public_key,
        )
        self.session.add(user)
        await self.session.flush()
        return await self._issue_tokens(user)

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self.session.scalar(
            select(User).where(User.email == data.email.lower())
        )
        if user is None or not verify_auth_hash(user.auth_hash, data.auth_hash):
            raise PermissionError("Invalid email or auth_hash")
        return await self._issue_tokens(user)

    async def _revoke_all_refresh_tokens(self, user_id: UUID, now: datetime) -> None:
        """Revoke every non-revoked refresh token for a user (session wipe)."""
        tokens = await self.session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        for token in tokens:
            token.revoked_at = now
        await self.session.flush()

    async def refresh(self, raw_token: str) -> TokenResponse:
        token_hash = _hash_refresh_token(raw_token)
        # Row lock serializes concurrent refresh of the same token.
        stored = await self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if stored is None:
            raise PermissionError("Invalid or expired refresh token")

        # Reuse of a rotated/revoked token is treated as theft: wipe all sessions.
        # Check revoked before expiry so an expired stolen token still triggers wipe.
        # Commit before raising so the wipe survives get_db's exception rollback.
        if stored.revoked_at is not None:
            await self._revoke_all_refresh_tokens(stored.user_id, now)
            await self.session.commit()
            raise PermissionError("Invalid or expired refresh token")

        if stored.expires_at <= now:
            raise PermissionError("Invalid or expired refresh token")

        # Rotate: revoke the presented token, then issue a fresh pair.
        stored.revoked_at = now
        user = await self.get_user(stored.user_id)
        if user is None:
            raise PermissionError("Invalid or expired refresh token")
        return await self._issue_tokens(user)

    async def revoke_refresh_token(self, raw_token: str) -> None:
        token_hash = _hash_refresh_token(raw_token)
        stored = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.session.flush()

    async def prelogin(self, data: PreloginRequest) -> PreloginResponse:
        user = await self.session.scalar(
            select(User).where(User.email == data.email.lower())
        )
        if user is None:
            raise LookupError("Unknown email")
        return PreloginResponse(salt=user.salt, kdf_params=user.kdf_params)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def rekey(self, user: User, data: RekeyRequest) -> User:
        if not verify_auth_hash(user.auth_hash, data.current_auth_hash):
            raise PermissionError("Invalid current auth_hash")

        now = datetime.now(UTC)
        user.auth_hash = data.auth_hash
        user.encrypted_vault_key = data.encrypted_vault_key
        if data.salt is not None:
            user.salt = data.salt
        if data.kdf_params is not None:
            user.kdf_params = data.kdf_params
        user.updated_at = now
        # Master-password change invalidates existing sessions.
        await self._revoke_all_refresh_tokens(user.id, now)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def delete_account(self, user: User, data: DeleteAccountRequest) -> None:
        if not verify_auth_hash(user.auth_hash, data.auth_hash):
            raise PermissionError("Invalid auth_hash")

        # Memberships / received shares use ON DELETE SET NULL — remove rows
        # so orphaned invite state does not linger after the user is gone.
        memberships = await self.session.scalars(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        for membership in memberships:
            await self.session.delete(membership)

        received = await self.session.scalars(
            select(Share).where(Share.recipient_user_id == user.id)
        )
        for share in received:
            await self.session.delete(share)

        await self.session.delete(user)
        await self.session.flush()
