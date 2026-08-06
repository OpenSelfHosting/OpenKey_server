"""Org create / invite / accept / roles / leave API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _second_user(client: AsyncClient, register_payload: dict) -> tuple[dict, dict]:
    other = {
        **register_payload,
        "email": f"member-{uuid.uuid4().hex}@example.com",
        "public_key": "member-public-key",
    }
    tokens = await register_and_login(client, other)
    return other, tokens


@pytest.mark.asyncio
async def test_org_create_invite_accept_leave(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    owner_tokens = await register_and_login(client, register_payload)
    member_payload, member_tokens = await _second_user(client, register_payload)
    org_uuid = str(uuid.uuid4())

    created = await client.post(
        "/orgs",
        headers=_auth(owner_tokens),
        json={
            "uuid": org_uuid,
            "encrypted_name": "enc-org-name",
            "wrapped_org_key": "wrapped-owner-key",
            "revision": 1,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["uuid"] == org_uuid
    assert created.json()["membership"]["role"] == "owner"
    assert created.json()["membership"]["status"] == "active"

    listed = await client.get("/orgs", headers=_auth(owner_tokens))
    assert listed.status_code == 200
    assert any(o["uuid"] == org_uuid for o in listed.json())

    invite = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": member_payload["email"],
            "role": "member",
            "wrapped_org_key": "wrapped-member-key",
        },
    )
    assert invite.status_code == 201, invite.text
    invite_id = invite.json()["id"]
    assert invite.json()["status"] == "invited"

    pending = await client.get("/invites/pending", headers=_auth(member_tokens))
    assert pending.status_code == 200
    assert any(i["id"] == invite_id for i in pending.json())

    accepted = await client.post(
        f"/invites/{invite_id}/accept",
        headers=_auth(member_tokens),
        json={},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"

    members = await client.get(
        f"/orgs/{org_uuid}/members",
        headers=_auth(member_tokens),
    )
    assert members.status_code == 200
    roles = {m["role"] for m in members.json() if m["status"] == "active"}
    assert "owner" in roles
    assert "member" in roles

    leave = await client.post(
        f"/orgs/{org_uuid}/leave",
        headers=_auth(member_tokens),
    )
    assert leave.status_code == 204

    gone = await client.get("/orgs", headers=_auth(member_tokens))
    assert all(o["uuid"] != org_uuid for o in gone.json())


@pytest.mark.asyncio
async def test_org_owner_cannot_leave_and_role_guardrails(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    owner_tokens = await register_and_login(client, register_payload)
    member_payload, member_tokens = await _second_user(client, register_payload)
    org_uuid = str(uuid.uuid4())

    await client.post(
        "/orgs",
        headers=_auth(owner_tokens),
        json={
            "uuid": org_uuid,
            "encrypted_name": "enc-org",
            "wrapped_org_key": "wrapped-owner",
            "revision": 1,
        },
    )

    owner_leave = await client.post(
        f"/orgs/{org_uuid}/leave",
        headers=_auth(owner_tokens),
    )
    assert owner_leave.status_code == 400

    invite = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": member_payload["email"],
            "role": "member",
            "wrapped_org_key": "wrapped-member",
        },
    )
    invite_id = invite.json()["id"]
    await client.post(
        f"/invites/{invite_id}/accept",
        headers=_auth(member_tokens),
        json={},
    )

    # Non-admin cannot invite.
    forbidden_invite = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(member_tokens),
        json={
            "email": f"extra-{uuid.uuid4().hex}@example.com",
            "role": "member",
            "wrapped_org_key": "wrapped",
        },
    )
    assert forbidden_invite.status_code == 403

    members = await client.get(
        f"/orgs/{org_uuid}/members",
        headers=_auth(owner_tokens),
    )
    member_row = next(
        m for m in members.json() if m["invited_email"] == member_payload["email"].lower()
    )

    promoted = await client.patch(
        f"/orgs/{org_uuid}/members/{member_row['id']}",
        headers=_auth(owner_tokens),
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    # Self-invite rejected.
    self_invite = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": register_payload["email"],
            "role": "member",
            "wrapped_org_key": "wrapped",
        },
    )
    assert self_invite.status_code == 400


@pytest.mark.asyncio
async def test_org_invite_revoke_and_duplicate_conflict(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    owner_tokens = await register_and_login(client, register_payload)
    member_payload, _member_tokens = await _second_user(client, register_payload)
    org_uuid = str(uuid.uuid4())

    await client.post(
        "/orgs",
        headers=_auth(owner_tokens),
        json={
            "uuid": org_uuid,
            "encrypted_name": "enc-org",
            "wrapped_org_key": "wrapped-owner",
            "revision": 1,
        },
    )

    invite = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": member_payload["email"],
            "role": "member",
            "wrapped_org_key": "wrapped-member",
        },
    )
    assert invite.status_code == 201
    invite_id = invite.json()["id"]

    dup = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": member_payload["email"],
            "role": "member",
            "wrapped_org_key": "wrapped-again",
        },
    )
    assert dup.status_code == 409

    revoked = await client.post(
        f"/orgs/{org_uuid}/invites/{invite_id}/revoke",
        headers=_auth(owner_tokens),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # Can re-invite after revoke.
    again = await client.post(
        f"/orgs/{org_uuid}/invites",
        headers=_auth(owner_tokens),
        json={
            "email": member_payload["email"],
            "role": "admin",
            "wrapped_org_key": "wrapped-reinvite",
        },
    )
    assert again.status_code == 201
    assert again.json()["role"] == "admin"
    assert again.json()["status"] == "invited"


@pytest.mark.asyncio
async def test_org_shared_entries_crud(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    org_uuid = str(uuid.uuid4())
    col_uuid = str(uuid.uuid4())
    entry_uuid = str(uuid.uuid4())

    await client.post(
        "/orgs",
        headers=headers,
        json={
            "uuid": org_uuid,
            "encrypted_name": "enc-org",
            "wrapped_org_key": "wrapped-owner",
            "revision": 1,
        },
    )
    created_col = await client.post(
        f"/orgs/{org_uuid}/collections",
        headers=headers,
        json={
            "uuid": col_uuid,
            "encrypted_name": "enc-col",
            "revision": 1,
        },
    )
    assert created_col.status_code == 201, created_col.text

    created = await client.post(
        f"/orgs/{org_uuid}/entries",
        headers=headers,
        json={
            "uuid": entry_uuid,
            "collection_uuid": col_uuid,
            "encrypted_payload": "enc-payload-v1",
            "revision": 1,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["encrypted_payload"] == "enc-payload-v1"
    assert created.json()["collection_uuid"] == col_uuid

    listed = await client.get(f"/orgs/{org_uuid}/entries", headers=headers)
    assert listed.status_code == 200
    assert any(e["uuid"] == entry_uuid for e in listed.json())

    patched = await client.patch(
        f"/orgs/{org_uuid}/entries/{entry_uuid}",
        headers=headers,
        json={"encrypted_payload": "enc-payload-v2", "revision": 2},
    )
    assert patched.status_code == 200
    assert patched.json()["encrypted_payload"] == "enc-payload-v2"
    assert patched.json()["revision"] == 2

    deleted = await client.delete(
        f"/orgs/{org_uuid}/entries/{entry_uuid}",
        headers=headers,
    )
    assert deleted.status_code == 204

    after = await client.get(f"/orgs/{org_uuid}/entries", headers=headers)
    assert all(e["uuid"] != entry_uuid for e in after.json())
