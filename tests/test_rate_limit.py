"""Unit tests for the sliding-window rate limiter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.rate_limit import SlidingWindowRateLimiter, client_ip


def test_allows_under_limit() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        limiter.check("k", limit=3, window_seconds=60)


def test_blocks_over_limit() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(2):
        limiter.check("k", limit=2, window_seconds=60)
    with pytest.raises(HTTPException) as exc:
        limiter.check("k", limit=2, window_seconds=60)
    assert exc.value.status_code == 429
    assert exc.value.headers is not None
    assert "Retry-After" in exc.value.headers


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter()
    limiter.check("a", limit=1, window_seconds=60)
    limiter.check("b", limit=1, window_seconds=60)
    with pytest.raises(HTTPException):
        limiter.check("a", limit=1, window_seconds=60)


def test_window_expiry_clears_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = SlidingWindowRateLimiter()
    now = 1_000.0

    def fake_monotonic() -> float:
        return now

    monkeypatch.setattr("app.rate_limit.time.monotonic", fake_monotonic)
    limiter.check("k", limit=1, window_seconds=10)
    with pytest.raises(HTTPException):
        limiter.check("k", limit=1, window_seconds=10)

    now = 1_011.0  # past window
    limiter.check("k", limit=1, window_seconds=10)


def test_zero_limit_always_blocks() -> None:
    limiter = SlidingWindowRateLimiter()
    with pytest.raises(HTTPException) as exc:
        limiter.check("k", limit=0, window_seconds=60)
    assert exc.value.status_code == 429


def test_client_ip_ignores_forwarded_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "c" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@localhost/z")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    get_settings.cache_clear()

    request = SimpleNamespace(
        headers={"x-forwarded-for": "9.9.9.9"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert client_ip(request) == "127.0.0.1"
    get_settings.cache_clear()


def test_client_ip_uses_forwarded_when_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "c" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@localhost/z")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()

    request = SimpleNamespace(
        headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert client_ip(request) == "9.9.9.9"
    get_settings.cache_clear()
