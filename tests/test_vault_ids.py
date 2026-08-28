"""Folder-id normalisation used by the app, extension, and CLI."""

from __future__ import annotations

from app.schemas.collection import CollectionCreate
from app.schemas.entry import EntryCreate
from app.schemas.sync import SyncCollectionItem, SyncEntryItem
from app.schemas.vault_ids import (
    RESERVED_COLLECTION_UUIDS,
    normalize_folder_id,
)


def test_normalize_root_sentinels() -> None:
    assert normalize_folder_id(None) is None
    assert normalize_folder_id("") is None
    assert normalize_folder_id("  ") is None
    assert normalize_folder_id("__root__") is None
    assert normalize_folder_id("null") is None
    assert normalize_folder_id(" __root__ ") is None


def test_normalize_keeps_reserved_and_uuids() -> None:
    for uuid in RESERVED_COLLECTION_UUIDS:
        assert normalize_folder_id(uuid) == uuid
    assert normalize_folder_id("folder-a") == "folder-a"


def test_entry_create_maps_root_sentinel() -> None:
    body = EntryCreate(
        uuid="e1",
        collection_uuid="__root__",
        encrypted_payload="cipher",
    )
    assert body.collection_uuid is None


def test_sync_items_map_root_sentinel() -> None:
    entry = SyncEntryItem(
        uuid="e1",
        collection_uuid="__root__",
        encrypted_payload="cipher",
        revision=1,
        is_deleted=False,
    )
    assert entry.collection_uuid is None
    col = SyncCollectionItem(
        uuid="c1",
        encrypted_name="enc",
        parent_uuid="__root__",
        revision=1,
        is_deleted=False,
    )
    assert col.parent_uuid is None


def test_collection_create_accepts_reserved_uuid() -> None:
    body = CollectionCreate(
        uuid="__wallets__",
        encrypted_name="enc-wallets",
        icon="material:account_balance_wallet",
    )
    assert body.uuid == "__wallets__"
    assert body.icon == "material:account_balance_wallet"
