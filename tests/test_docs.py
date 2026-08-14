"""Docs portal smoke tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_docs_overview(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "OpenKey Sync API" in body
    assert "/docs/reference" in body
    assert "Zero-knowledge" in body


@pytest.mark.asyncio
async def test_docs_reference(client: AsyncClient) -> None:
    response = await client.get("/docs/reference")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "scalar" in response.text.lower()


@pytest.mark.asyncio
async def test_openapi_json(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "OpenKey Sync API"
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    assert any(tag["name"] == "auth" for tag in schema["tags"])


@pytest.mark.asyncio
async def test_legacy_docs_redirects(client: AsyncClient) -> None:
    for path in ("/redoc", "/swagger"):
        response = await client.get(path, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/docs/reference"
