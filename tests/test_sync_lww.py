"""Sync LWW-by-revision and soft-delete tombstone behavior."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_sync_lww_higher_revision_wins(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    entry_uuid = str(uuid.uuid4())
    col_uuid = str(uuid.uuid4())

    first = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [
                {
                    "uuid": col_uuid,
                    "encrypted_name": "col-v1",
                    "icon": "material:folder",
                    "parent_uuid": None,
                    "sort_order": 0,
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "payload-v1",
                    "revision": 2,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert first.status_code == 200, first.text

    # Older revision must not overwrite.
    stale = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "payload-stale",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert stale.status_code == 200
    entry = next(e for e in stale.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["encrypted_payload"] == "payload-v1"
    assert entry["revision"] == 2

    # Equal revision with different ciphertext updates; identical is a no-op.
    equal = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "payload-equal",
                    "revision": 2,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert equal.status_code == 200
    entry = next(e for e in equal.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["encrypted_payload"] == "payload-equal"
    updated_after_equal = entry["updated_at"]

    # Identical equal-revision push must not churn updated_at / appear in delta.
    cursor = equal.json()["server_revision"]
    noop = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": cursor,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "payload-equal",
                    "revision": 2,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert noop.status_code == 200
    noop_entries = [
        e for e in noop.json()["entries"] if e["uuid"] == entry_uuid
    ]
    assert noop_entries == []
    # Confirm payload unchanged when re-pulled from 0.
    full = await client.post(
        "/sync",
        headers=headers,
        json={"since_revision": 0, "collections": [], "entries": []},
    )
    entry = next(e for e in full.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["encrypted_payload"] == "payload-equal"
    assert entry["updated_at"] == updated_after_equal

    # Higher revision wins.
    newer = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [
                {
                    "uuid": col_uuid,
                    "encrypted_name": "col-v2",
                    "icon": "material:folder",
                    "parent_uuid": None,
                    "sort_order": 1,
                    "revision": 2,
                    "is_deleted": False,
                }
            ],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "payload-v2",
                    "revision": 3,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert newer.status_code == 200
    entry = next(e for e in newer.json()["entries"] if e["uuid"] == entry_uuid)
    col = next(c for c in newer.json()["collections"] if c["uuid"] == col_uuid)
    assert entry["encrypted_payload"] == "payload-v2"
    assert entry["revision"] == 3
    assert col["encrypted_name"] == "col-v2"
    assert col["revision"] == 2


@pytest.mark.asyncio
async def test_sync_soft_delete_tombstone(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    entry_uuid = str(uuid.uuid4())

    await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": None,
                    "encrypted_payload": "alive",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )

    tombstone = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": None,
                    "encrypted_payload": "alive",
                    "revision": 2,
                    "is_deleted": True,
                }
            ],
        },
    )
    assert tombstone.status_code == 200
    entry = next(e for e in tombstone.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["is_deleted"] is True
    assert entry["revision"] == 2

    # CRUD list hides soft-deleted entries.
    listed = await client.get("/entries", headers=headers)
    assert listed.status_code == 200
    assert all(e["uuid"] != entry_uuid for e in listed.json())

    # Lower-revision undelete must not resurrect.
    stale_revive = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": None,
                    "encrypted_payload": "zombie",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert stale_revive.status_code == 200
    entry = next(e for e in stale_revive.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["is_deleted"] is True
    assert entry["revision"] == 2


@pytest.mark.asyncio
async def test_sync_echoes_winner_on_stale_push_with_recent_cursor(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    """Stale LWW losers must still see the winning row even with a fresh cursor."""
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    entry_uuid = str(uuid.uuid4())

    first = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": None,
                    "encrypted_payload": "winner",
                    "revision": 5,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert first.status_code == 200
    cursor = first.json()["server_revision"]
    assert cursor > 0

    stale = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": cursor,
            "collections": [],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": None,
                    "encrypted_payload": "loser",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert stale.status_code == 200
    entry = next(e for e in stale.json()["entries"] if e["uuid"] == entry_uuid)
    assert entry["encrypted_payload"] == "winner"
    assert entry["revision"] == 5
