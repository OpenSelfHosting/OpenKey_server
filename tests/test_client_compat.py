"""Client-compat tests: reserved collections, custom icons, CORS, ARGB colors.

Matches OpenKey app / extension / CLI 1.0.6 payloads.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


CHROME_EXT_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
FIREFOX_EXT_ORIGIN = "moz-extension://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.mark.asyncio
async def test_sync_reserved_collections_and_typed_entries(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    """Cards / crypto / secrets live in reserved collection namespaces."""
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    reserved = [
        ("__wallets__", "material:account_balance_wallet"),
        ("__crypto_wallets__", "material:currency_bitcoin"),
        ("__dev_secrets__", "material:terminal"),
    ]
    collections = [
        {
            "uuid": uuid_,
            "encrypted_name": f"enc-{uuid_}",
            "icon": icon,
            "parent_uuid": None,
            "sort_order": i,
            "revision": 1,
            "is_deleted": False,
        }
        for i, (uuid_, icon) in enumerate(reserved)
    ]
    entries = [
        {
            "uuid": str(uuid.uuid4()),
            "collection_uuid": col["uuid"],
            "encrypted_payload": f"cipher-{col['uuid']}",
            "revision": 1,
            "is_deleted": False,
        }
        for col in collections
    ]

    push = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": collections,
            "entries": entries,
        },
    )
    assert push.status_code == 200, push.text
    body = push.json()
    got_cols = {c["uuid"]: c for c in body["collections"]}
    for uuid_, icon in reserved:
        assert uuid_ in got_cols
        assert got_cols[uuid_]["icon"] == icon
    got_entries = {e["collection_uuid"] for e in body["entries"]}
    assert got_entries == {c["uuid"] for c in collections}


@pytest.mark.asyncio
async def test_sync_custom_folder_icon_and_argb_color(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    """Pro custom icons exceed VARCHAR(255); Flutter ARGB exceeds INT4."""
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    col_uuid = str(uuid.uuid4())
    # Longer than the old VARCHAR(255) column, shorter than CustomIcons cap.
    icon = "custom:png:" + ("A" * 300)
    color = 0xFF6750A4  # 4284960932 — does not fit signed 32-bit INTEGER

    push = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [
                {
                    "uuid": col_uuid,
                    "encrypted_name": "enc-custom",
                    "icon": icon,
                    "color": color,
                    "parent_uuid": None,
                    "sort_order": 0,
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
            "entries": [],
        },
    )
    assert push.status_code == 200, push.text
    row = next(c for c in push.json()["collections"] if c["uuid"] == col_uuid)
    assert row["icon"] == icon
    assert row["color"] == color


@pytest.mark.asyncio
async def test_sync_root_sentinel_becomes_null(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    entry_uuid = str(uuid.uuid4())
    col_uuid = str(uuid.uuid4())

    push = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [
                {
                    "uuid": col_uuid,
                    "encrypted_name": "enc-top",
                    "parent_uuid": "__root__",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": "__root__",
                    "encrypted_payload": "cipher",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert push.status_code == 200, push.text
    col = next(c for c in push.json()["collections"] if c["uuid"] == col_uuid)
    entry = next(e for e in push.json()["entries"] if e["uuid"] == entry_uuid)
    assert col["parent_uuid"] is None
    assert entry["collection_uuid"] is None


@pytest.mark.asyncio
async def test_patch_collection_keeps_parent_when_omitted(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    parent = str(uuid.uuid4())
    child = str(uuid.uuid4())
    for col_uuid, parent_uuid in ((parent, None), (child, parent)):
        created = await client.post(
            "/collections",
            headers=headers,
            json={
                "uuid": col_uuid,
                "encrypted_name": f"enc-{col_uuid}",
                "parent_uuid": parent_uuid,
                "revision": 1,
            },
        )
        assert created.status_code == 201, created.text

    patched = await client.patch(
        f"/collections/{child}",
        headers=headers,
        json={"encrypted_name": "enc-renamed", "revision": 2},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["parent_uuid"] == parent
    assert patched.json()["encrypted_name"] == "enc-renamed"


@pytest.mark.asyncio
async def test_cors_allows_browser_extension_origins(client: AsyncClient) -> None:
    for origin in (CHROME_EXT_ORIGIN, FIREFOX_EXT_ORIGIN):
        preflight = await client.options(
            "/auth/prelogin",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code in (200, 204)
        assert preflight.headers.get("access-control-allow-origin") == origin

        health = await client.get("/health", headers={"Origin": origin})
        assert health.status_code == 200
        assert health.headers.get("access-control-allow-origin") == origin
