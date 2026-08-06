"""Attachment multipart upload / download / soft-delete tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_attachment_upload_download_soft_delete(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    att_uuid = str(uuid.uuid4())
    entry_uuid = str(uuid.uuid4())
    blob = b"ciphertext-bytes-not-plaintext"

    upload = await client.post(
        "/attachments",
        headers=headers,
        data={
            "uuid": att_uuid,
            "entry_uuid": entry_uuid,
            "filename": "note.bin.enc",
            "size_bytes": str(len(blob)),
            "revision": "1",
            "content_type": "application/octet-stream",
        },
        files={"file": ("note.bin.enc", blob, "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text
    meta = upload.json()
    assert meta["uuid"] == att_uuid
    assert meta["entry_uuid"] == entry_uuid
    assert meta["size_bytes"] == len(blob)
    assert meta["is_deleted"] is False
    assert "encrypted_blob" not in meta  # metadata endpoint must not leak blob field

    listed = await client.get("/attachments", headers=headers)
    assert listed.status_code == 200
    assert any(a["uuid"] == att_uuid for a in listed.json())

    got = await client.get(f"/attachments/{att_uuid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["filename"] == "note.bin.enc"

    content = await client.get(f"/attachments/{att_uuid}/content", headers=headers)
    assert content.status_code == 200
    assert content.content == blob
    assert content.headers["content-type"].startswith("application/octet-stream")
    assert content.headers["x-openkey-entry-uuid"] == entry_uuid

    deleted = await client.delete(f"/attachments/{att_uuid}", headers=headers)
    assert deleted.status_code == 204

    # Soft-deleted: hidden from list/get/content.
    listed_after = await client.get("/attachments", headers=headers)
    assert all(a["uuid"] != att_uuid for a in listed_after.json())

    missing = await client.get(f"/attachments/{att_uuid}", headers=headers)
    assert missing.status_code == 404

    missing_content = await client.get(
        f"/attachments/{att_uuid}/content",
        headers=headers,
    )
    assert missing_content.status_code == 404


@pytest.mark.asyncio
async def test_attachment_size_mismatch_and_duplicate(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    tokens = await register_and_login(client, register_payload)
    headers = _auth(tokens)
    att_uuid = str(uuid.uuid4())
    blob = b"abc"

    bad_size = await client.post(
        "/attachments",
        headers=headers,
        data={
            "uuid": att_uuid,
            "entry_uuid": str(uuid.uuid4()),
            "filename": "x.bin",
            "size_bytes": "99",
            "revision": "1",
        },
        files={"file": ("x.bin", blob, "application/octet-stream")},
    )
    assert bad_size.status_code == 400

    ok = await client.post(
        "/attachments",
        headers=headers,
        data={
            "uuid": att_uuid,
            "entry_uuid": str(uuid.uuid4()),
            "filename": "x.bin",
            "size_bytes": str(len(blob)),
            "revision": "1",
        },
        files={"file": ("x.bin", blob, "application/octet-stream")},
    )
    assert ok.status_code == 201

    dup = await client.post(
        "/attachments",
        headers=headers,
        data={
            "uuid": att_uuid,
            "entry_uuid": str(uuid.uuid4()),
            "filename": "y.bin",
            "size_bytes": str(len(blob)),
            "revision": "1",
        },
        files={"file": ("y.bin", blob, "application/octet-stream")},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_attachment_isolation_between_users(
    client: AsyncClient,
    register_payload: dict,
) -> None:
    owner_tokens = await register_and_login(client, register_payload)
    other = {
        **register_payload,
        "email": f"other-{uuid.uuid4().hex}@example.com",
        "public_key": "other-pk",
    }
    other_tokens = await register_and_login(client, other)

    att_uuid = str(uuid.uuid4())
    blob = b"secret-cipher"
    upload = await client.post(
        "/attachments",
        headers=_auth(owner_tokens),
        data={
            "uuid": att_uuid,
            "entry_uuid": str(uuid.uuid4()),
            "filename": "a.bin",
            "size_bytes": str(len(blob)),
            "revision": "1",
        },
        files={"file": ("a.bin", blob, "application/octet-stream")},
    )
    assert upload.status_code == 201

    steal = await client.get(
        f"/attachments/{att_uuid}/content",
        headers=_auth(other_tokens),
    )
    assert steal.status_code == 404
