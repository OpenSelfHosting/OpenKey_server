"""Shared fixtures for OpenKey server tests.

Environment must be set *before* importing `app` modules that call
`get_settings()` at import time (`app.db.session`, `app.main`).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

# Prefer a dedicated test database so local/dev data is never wiped.
# Override with TEST_DATABASE_URL when needed (CI sets DATABASE_URL directly).
_DEFAULT_DB = "postgresql+asyncpg://openkey:openkey@localhost:5432/openkey_test"
if "TEST_DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
elif "CI" in os.environ and "DATABASE_URL" in os.environ:
    # GitHub Actions already points DATABASE_URL at the test DB.
    pass
else:
    os.environ["DATABASE_URL"] = _DEFAULT_DB
os.environ.setdefault(
    "JWT_SECRET",
    "test-jwt-secret-key-at-least-32-chars-long!!",
)
os.environ.setdefault("AUTH_RATE_LIMIT_REQUESTS", "1000")
os.environ.setdefault("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
os.environ.setdefault(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.rate_limit import auth_rate_limiter

get_settings.cache_clear()


def _admin_database_url(database_url: str) -> str:
    """Swap the DB name for the default `postgres` maintenance database."""
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path="/postgres"))


async def _ensure_database_exists(database_url: str) -> None:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") or "openkey_test"
    admin_url = _admin_database_url(database_url)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """Create the test DB if needed and apply Alembic migrations."""
    import asyncio

    from app.db.migrate import run_migrations

    get_settings.cache_clear()
    asyncio.run(_ensure_database_exists(get_settings().database_url))
    run_migrations()


@pytest.fixture(autouse=True)
def _clear_rate_limiter() -> None:
    auth_rate_limiter._hits.clear()


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


@pytest.fixture
def register_payload(unique_email: str) -> dict:
    return {
        "email": unique_email,
        "auth_hash": "test-auth-hash-value",
        "encrypted_vault_key": "ciphertext-vault-key",
        "kdf_params": {
            "algorithm": "argon2id",
            "memory": 65536,
            "iterations": 3,
            "parallelism": 4,
            "hashLength": 32,
        },
        "salt": "dGVzdC1zYWx0",
        "public_key": "dGVzdC1wdWJrZXk",
    }


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # Import after env + migrations so engine/settings pick up test values.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_and_login(
    client: AsyncClient,
    payload: dict,
) -> dict:
    """Register a user and return the token response JSON."""
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
