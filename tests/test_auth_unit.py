"""Unit tests for auth helpers (no database)."""

from __future__ import annotations

from uuid import uuid4

import jwt
import pytest

from app.config import Settings
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    verify_auth_hash,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-key-32chars!",
        database_url="postgresql+asyncpg://x:y@localhost/z",
        access_token_expire_minutes=15,
    )


def test_verify_auth_hash_match() -> None:
    assert verify_auth_hash("abc", "abc") is True


def test_verify_auth_hash_ignores_base64_padding() -> None:
    assert verify_auth_hash("abcd==", "abcd") is True
    assert verify_auth_hash("abcd", "abcd=") is True


def test_verify_auth_hash_mismatch() -> None:
    assert verify_auth_hash("abc", "abd") is False


def test_verify_auth_hash_different_lengths() -> None:
    assert verify_auth_hash("short", "much-longer-value") is False


def test_create_and_decode_access_token(test_settings: Settings) -> None:
    user_id = uuid4()
    token, expires_in = create_access_token(user_id, test_settings)
    assert expires_in == 15 * 60
    assert decode_access_token(token, test_settings) == user_id


def test_decode_rejects_wrong_type(test_settings: Settings) -> None:
    user_id = uuid4()
    bad = jwt.encode(
        {"sub": str(user_id), "type": "refresh"},
        test_settings.jwt_secret,
        algorithm=test_settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError, match="Not an access token"):
        decode_access_token(bad, test_settings)


def test_decode_rejects_missing_sub(test_settings: Settings) -> None:
    bad = jwt.encode(
        {"type": "access"},
        test_settings.jwt_secret,
        algorithm=test_settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError, match="missing subject"):
        decode_access_token(bad, test_settings)


def test_decode_rejects_tampered_token(test_settings: Settings) -> None:
    user_id = uuid4()
    token, _ = create_access_token(user_id, test_settings)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "x", test_settings)
