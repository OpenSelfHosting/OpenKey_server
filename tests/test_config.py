"""Unit tests for Settings validation (no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_rejects_insecure_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="change-me-to-a-long-random-secret",
            database_url="postgresql+asyncpg://x:y@localhost/z",
        )


def test_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="too-short",
            database_url="postgresql+asyncpg://x:y@localhost/z",
        )


def test_accepts_strong_jwt_secret() -> None:
    settings = Settings(
        jwt_secret="a" * 32,
        database_url="postgresql+asyncpg://x:y@localhost/z",
        cors_origins="http://localhost:3000",
    )
    assert settings.jwt_secret == "a" * 32
    assert settings.cors_origin_list == ["http://localhost:3000"]


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValidationError, match="must not include"):
        Settings(
            jwt_secret="a" * 32,
            database_url="postgresql+asyncpg://x:y@localhost/z",
            cors_origins="*",
        )


def test_cors_rejects_empty() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        Settings(
            jwt_secret="a" * 32,
            database_url="postgresql+asyncpg://x:y@localhost/z",
            cors_origins="  ,  ",
        )


def test_cors_extension_regex_matches_chrome_and_firefox() -> None:
    import re

    settings = Settings(
        jwt_secret="a" * 32,
        database_url="postgresql+asyncpg://x:y@localhost/z",
        cors_origins="http://localhost:3000",
    )
    regex = re.compile(settings.cors_origin_regex or "")
    assert regex.match("chrome-extension://abcdefghijklmnopabcdefghijklmnop")
    assert regex.match("moz-extension://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert not regex.match("https://evil.example")
    assert not regex.match("chrome-extension://not-a-valid-id")


def test_cors_extension_regex_can_be_disabled() -> None:
    settings = Settings(
        jwt_secret="a" * 32,
        database_url="postgresql+asyncpg://x:y@localhost/z",
        cors_origins="http://localhost:3000",
        cors_allow_browser_extensions=False,
    )
    assert settings.cors_origin_regex is None


def test_get_settings_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "b" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@localhost/z")
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
    get_settings.cache_clear()
