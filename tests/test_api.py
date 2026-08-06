"""API integration tests: health + auth + vault + sync.

Requires a reachable PostgreSQL matching DATABASE_URL (see conftest / CI).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_all_sessions(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    """Presenting a rotated refresh token must wipe every session for that user."""
    tokens = await register_and_login(client, register_payload)
    first_refresh = tokens["refresh_token"]

    rotated = await client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotated.status_code == 200
    current_refresh = rotated.json()["refresh_token"]

    # Steal/reuse the old token after rotation.
    reuse = await client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert reuse.status_code == 401

    # The legitimate post-rotation token must also be dead.
    after_reuse = await client.post(
        "/auth/refresh",
        json={"refresh_token": current_refresh},
    )
    assert after_reuse.status_code == 401


@pytest.mark.asyncio
async def test_register_login_prelogin_me(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] > 0

    pre = await client.post(
        "/auth/prelogin",
        json={"email": register_payload["email"]},
    )
    assert pre.status_code == 200
    assert pre.json()["salt"] == register_payload["salt"]
    assert pre.json()["kdf_params"] == register_payload["kdf_params"]

    login = await client.post(
        "/auth/login",
        json={
            "email": register_payload["email"],
            "auth_hash": register_payload["auth_hash"],
        },
    )
    assert login.status_code == 200
    assert "access_token" in login.json()

    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == register_payload["email"].lower()
    assert body["encrypted_vault_key"] == register_payload["encrypted_vault_key"]
    assert body["salt"] == register_payload["salt"]


@pytest.mark.asyncio
async def test_register_duplicate_conflict(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    await register_and_login(client, register_payload)
    again = await client.post("/auth/register", json=register_payload)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_hash(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    await register_and_login(client, register_payload)
    bad = await client.post(
        "/auth/login",
        json={"email": register_payload["email"], "auth_hash": "wrong"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_prelogin_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/prelogin",
        json={"email": f"missing-{uuid.uuid4().hex}@example.com"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refresh_rotates_and_logout(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    old_refresh = tokens["refresh_token"]

    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != old_refresh

    # Old refresh token is revoked after rotation.
    reuse = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert reuse.status_code == 401

    logout = await client.post(
        "/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout.status_code == 204

    after_logout = await client.post(
        "/auth/refresh",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rekey_and_delete(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    rekey = await client.post(
        "/auth/rekey",
        headers=headers,
        json={
            "current_auth_hash": register_payload["auth_hash"],
            "auth_hash": "new-auth-hash",
            "encrypted_vault_key": "new-wrapped-key",
        },
    )
    assert rekey.status_code == 200
    assert rekey.json()["encrypted_vault_key"] == "new-wrapped-key"

    # Rekey must invalidate existing refresh sessions.
    stale_refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert stale_refresh.status_code == 401

    # Old hash no longer works.
    old_login = await client.post(
        "/auth/login",
        json={
            "email": register_payload["email"],
            "auth_hash": register_payload["auth_hash"],
        },
    )
    assert old_login.status_code == 401

    delete = await client.post(
        "/auth/delete",
        headers=headers,
        json={"auth_hash": "new-auth-hash"},
    )
    assert delete.status_code == 204

    gone = await client.post(
        "/auth/login",
        json={"email": register_payload["email"], "auth_hash": "new-auth-hash"},
    )
    assert gone.status_code == 401


@pytest.mark.asyncio
async def test_collections_and_entries_crud(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    col_uuid = str(uuid.uuid4())
    entry_uuid = str(uuid.uuid4())

    created = await client.post(
        "/collections",
        headers=headers,
        json={
            "uuid": col_uuid,
            "encrypted_name": "enc-folder",
            "icon": "material:folder",
            "sort_order": 0,
            "revision": 1,
        },
    )
    assert created.status_code == 201
    assert created.json()["uuid"] == col_uuid

    listed = await client.get("/collections", headers=headers)
    assert listed.status_code == 200
    assert any(c["uuid"] == col_uuid for c in listed.json())

    entry = await client.post(
        "/entries",
        headers=headers,
        json={
            "uuid": entry_uuid,
            "collection_uuid": col_uuid,
            "encrypted_payload": "enc-payload",
            "revision": 1,
        },
    )
    assert entry.status_code == 201

    dangling = await client.post(
        "/entries",
        headers=headers,
        json={
            "uuid": str(uuid.uuid4()),
            "collection_uuid": str(uuid.uuid4()),
            "encrypted_payload": "enc-payload",
            "revision": 1,
        },
    )
    assert dangling.status_code == 400

    patched = await client.patch(
        f"/entries/{entry_uuid}",
        headers=headers,
        json={"encrypted_payload": "enc-payload-v2", "revision": 2},
    )
    assert patched.status_code == 200
    assert patched.json()["encrypted_payload"] == "enc-payload-v2"
    assert patched.json()["revision"] == 2

    deleted = await client.delete(f"/entries/{entry_uuid}", headers=headers)
    assert deleted.status_code == 204

    entries = await client.get("/entries", headers=headers)
    assert entries.status_code == 200
    assert all(e["uuid"] != entry_uuid for e in entries.json())


@pytest.mark.asyncio
async def test_sync_push_and_pull(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    col_uuid = str(uuid.uuid4())
    entry_uuid = str(uuid.uuid4())

    push = await client.post(
        "/sync",
        headers=headers,
        json={
            "since_revision": 0,
            "collections": [
                {
                    "uuid": col_uuid,
                    "encrypted_name": "sync-col",
                    "icon": "material:folder",
                    "parent_uuid": None,
                    "sort_order": 1,
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
            "entries": [
                {
                    "uuid": entry_uuid,
                    "collection_uuid": col_uuid,
                    "encrypted_payload": "sync-entry",
                    "revision": 1,
                    "is_deleted": False,
                }
            ],
        },
    )
    assert push.status_code == 200
    body = push.json()
    assert body["server_revision"] > 0
    assert any(c["uuid"] == col_uuid for c in body["collections"])
    assert any(e["uuid"] == entry_uuid for e in body["entries"])

    # Full pull again with empty push should still return items.
    pull = await client.post(
        "/sync",
        headers=headers,
        json={"since_revision": 0, "collections": [], "entries": []},
    )
    assert pull.status_code == 200
    assert any(c["uuid"] == col_uuid for c in pull.json()["collections"])


@pytest.mark.asyncio
async def test_lookup_public_key(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Second user to look up.
    other = {
        **register_payload,
        "email": f"other-{uuid.uuid4().hex}@example.com",
        "public_key": "other-public-key",
    }
    await register_and_login(client, other)

    found = await client.post(
        "/auth/lookup-public-key",
        headers=headers,
        json={"email": other["email"]},
    )
    assert found.status_code == 200
    assert found.json()["public_key"] == "other-public-key"
    assert found.json()["email"] == other["email"].lower()
