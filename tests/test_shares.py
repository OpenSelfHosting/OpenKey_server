"""Share create / accept / revoke + snapshot semantics."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _other_user(client: AsyncClient, register_payload: dict) -> tuple[dict, dict]:
    other = {
        **register_payload,
        "email": f"sharee-{uuid.uuid4().hex}@example.com",
        "public_key": "sharee-pubkey",
    }
    return other, await register_and_login(client, other)


@pytest.mark.asyncio
async def test_share_create_accept_revoke_snapshot(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    owner_tokens = await register_and_login(client, register_payload)
    recipient_payload, recipient_tokens = await _other_user(client, register_payload)
    share_uuid = str(uuid.uuid4())
    entry_uuid = str(uuid.uuid4())
    snapshot = "frozen-ciphertext-v1"

    created = await client.post(
        "/shares",
        headers=_auth(owner_tokens),
        json={
            "uuid": share_uuid,
            "recipient_email": recipient_payload["email"],
            "entry_uuid": entry_uuid,
            "wrapped_item_key": "wrapped-item-key",
            "encrypted_payload": snapshot,
            "revision": 1,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["encrypted_payload"] == snapshot
    assert body["entry_uuid"] == entry_uuid

    listed = await client.get("/shares", headers=_auth(recipient_tokens))
    assert listed.status_code == 200
    assert any(s["uuid"] == share_uuid for s in listed.json())

    # Non-recipient cannot accept.
    stranger = {
        **register_payload,
        "email": f"stranger-{uuid.uuid4().hex}@example.com",
        "public_key": "stranger-pk",
    }
    stranger_tokens = await register_and_login(client, stranger)
    forbidden = await client.post(
        f"/shares/{share_uuid}/accept",
        headers=_auth(stranger_tokens),
    )
    assert forbidden.status_code == 403

    accepted = await client.post(
        f"/shares/{share_uuid}/accept",
        headers=_auth(recipient_tokens),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    # Snapshot payload is unchanged by accept (point-in-time, not live sync).
    assert accepted.json()["encrypted_payload"] == snapshot

    # Accepting again fails.
    again = await client.post(
        f"/shares/{share_uuid}/accept",
        headers=_auth(recipient_tokens),
    )
    assert again.status_code == 400

    # Recipient cannot revoke.
    recipient_revoke = await client.post(
        f"/shares/{share_uuid}/revoke",
        headers=_auth(recipient_tokens),
    )
    assert recipient_revoke.status_code == 403

    revoked = await client.post(
        f"/shares/{share_uuid}/revoke",
        headers=_auth(owner_tokens),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # Revoked shares disappear from list filters.
    after = await client.get("/shares", headers=_auth(owner_tokens))
    assert all(s["uuid"] != share_uuid for s in after.json())


@pytest.mark.asyncio
async def test_entry_share_requires_snapshot_payload(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    missing = await client.post(
        "/shares",
        headers=_auth(tokens),
        json={
            "uuid": str(uuid.uuid4()),
            "recipient_email": f"r-{uuid.uuid4().hex}@example.com",
            "entry_uuid": str(uuid.uuid4()),
            "wrapped_item_key": "wrapped",
            "revision": 1,
        },
    )
    assert missing.status_code == 422

    blank = await client.post(
        "/shares",
        headers=_auth(tokens),
        json={
            "uuid": str(uuid.uuid4()),
            "recipient_email": f"r-{uuid.uuid4().hex}@example.com",
            "entry_uuid": str(uuid.uuid4()),
            "wrapped_item_key": "wrapped",
            "encrypted_payload": "   ",
            "revision": 1,
        },
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_cannot_share_with_self_and_revoke_pending(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    self_share = await client.post(
        "/shares",
        headers=_auth(tokens),
        json={
            "uuid": str(uuid.uuid4()),
            "recipient_email": register_payload["email"],
            "entry_uuid": str(uuid.uuid4()),
            "wrapped_item_key": "wrapped",
            "encrypted_payload": "snap",
            "revision": 1,
        },
    )
    assert self_share.status_code == 400

    other = {
        **register_payload,
        "email": f"pending-{uuid.uuid4().hex}@example.com",
        "public_key": "pk",
    }
    await register_and_login(client, other)
    share_uuid = str(uuid.uuid4())
    created = await client.post(
        "/shares",
        headers=_auth(tokens),
        json={
            "uuid": share_uuid,
            "recipient_email": other["email"],
            "entry_uuid": str(uuid.uuid4()),
            "wrapped_item_key": "wrapped",
            "encrypted_payload": "snap",
            "revision": 1,
        },
    )
    assert created.status_code == 201

    revoked = await client.post(
        f"/shares/{share_uuid}/revoke",
        headers=_auth(tokens),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # Accept after revoke fails.
    other_tokens = (
        await client.post(
            "/auth/login",
            json={"email": other["email"], "auth_hash": other["auth_hash"]},
        )
    ).json()
    accept = await client.post(
        f"/shares/{share_uuid}/accept",
        headers=_auth(other_tokens),
    )
    assert accept.status_code == 400
