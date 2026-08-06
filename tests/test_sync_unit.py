"""Unit tests for sync cursor helpers and attachment size validation."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.sync import (
    _datetime_to_revision,
    _since_to_datetime,
    _upsert_attachment_row,
)


def test_since_zero_is_epoch() -> None:
    assert _since_to_datetime(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert _since_to_datetime(-1) == datetime(1970, 1, 1, tzinfo=UTC)


def test_since_microseconds_round_trip() -> None:
    original = datetime(2024, 6, 15, 12, 30, 45, 123456, tzinfo=UTC)
    rev = _datetime_to_revision(original)
    restored = _since_to_datetime(rev)
    assert restored == original


def test_datetime_none_is_zero() -> None:
    assert _datetime_to_revision(None) == 0


def test_naive_datetime_assumes_utc() -> None:
    naive = datetime(2024, 1, 1, 0, 0, 0)
    rev = _datetime_to_revision(naive)
    assert rev == _datetime_to_revision(naive.replace(tzinfo=UTC))


def test_attachment_size_bytes_zero_does_not_bypass_mismatch() -> None:
    """size_bytes=0 must not be treated as missing and replaced with blob length."""
    blob = b"ciphertext"
    item = SimpleNamespace(
        uuid=str(uuid4()),
        entry_uuid=str(uuid4()),
        filename="x.enc",
        size_bytes=0,  # falsy but explicit
        content_type="application/octet-stream",
        revision=1,
        is_deleted=False,
        encrypted_blob=base64.b64encode(blob).decode("ascii"),
    )
    with pytest.raises(HTTPException) as exc:
        _upsert_attachment_row(None, uuid4(), item, datetime.now(UTC))
    assert exc.value.status_code == 400
    assert "size_bytes mismatch" in exc.value.detail
