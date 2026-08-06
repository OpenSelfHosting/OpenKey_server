from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    auth_hash: str = Field(min_length=1)
    encrypted_vault_key: str = Field(min_length=1)
    kdf_params: dict[str, Any]
    salt: str = Field(min_length=1)
    public_key: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    auth_hash: str = Field(min_length=1)


class PreloginRequest(BaseModel):
    email: EmailStr


class PreloginResponse(BaseModel):
    """Public KDF bootstrap so clients can derive auth_hash before login.

    Salt and kdf_params are not secrets; the master password never leaves the
    client. encrypted_vault_key stays behind authenticated /auth/me.
    """

    salt: str
    kdf_params: dict[str, Any]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: UUID
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class DeleteAccountRequest(BaseModel):
    auth_hash: str = Field(min_length=1)


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: EmailStr
    public_key: str | None = None
    encrypted_private_key: str | None = None
    # Opaque unlock bootstrap for clients (extension / new devices).
    # Still zero-knowledge: ciphertext + salt + KDF params only.
    salt: str
    encrypted_vault_key: str
    kdf_params: dict[str, Any]


class KeysUpdateRequest(BaseModel):
    public_key: str = Field(min_length=1)
    encrypted_private_key: str = Field(min_length=1)


class RekeyRequest(BaseModel):
    """Client-side master-password change (rekey).

    The vault key itself is unchanged; only the wrapped vault key and auth_hash
    are rotated. The server never sees the master password.
    """

    current_auth_hash: str = Field(min_length=1)
    auth_hash: str = Field(min_length=1)
    encrypted_vault_key: str = Field(min_length=1)
    salt: str | None = Field(default=None, min_length=1)
    kdf_params: dict[str, Any] | None = None


class PublicKeyLookupRequest(BaseModel):
    email: EmailStr


class PublicKeyLookupResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    public_key: str | None = None


# Alias used by some clients / OpenAPI docs
AuthResponse = TokenResponse
