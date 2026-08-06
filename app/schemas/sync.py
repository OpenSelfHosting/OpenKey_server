from pydantic import BaseModel, Field

from app.schemas.attachment import AttachmentResponse, MAX_ATTACHMENT_BYTES
from app.schemas.collection import CollectionResponse
from app.schemas.entry import EntryResponse


class SyncCollectionItem(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    encrypted_name: str = Field(min_length=1)
    icon: str = "material:folder"
    color: int | None = None
    parent_uuid: str | None = Field(default=None, max_length=64)
    sort_order: int = 0
    revision: int = Field(default=1, ge=1)
    is_deleted: bool = False


class SyncEntryItem(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    collection_uuid: str | None = None
    encrypted_payload: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    is_deleted: bool = False


class SyncAttachmentItem(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    entry_uuid: str = Field(min_length=1, max_length=64)
    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0, le=MAX_ATTACHMENT_BYTES)
    content_type: str | None = Field(default=None, max_length=255)
    revision: int = Field(default=1, ge=1)
    is_deleted: bool = False
    encrypted_blob: str = Field(min_length=1, description="Base64-encoded ciphertext")


class SyncRequest(BaseModel):
    since_revision: int | None = Field(
        default=0,
        ge=0,
        description="Sync cursor: unix microseconds of last seen updated_at (0 = full pull)",
    )
    collections: list[SyncCollectionItem] | None = None
    entries: list[SyncEntryItem] | None = None
    attachments: list[SyncAttachmentItem] | None = None


SyncPushItem = SyncCollectionItem


class SyncResponse(BaseModel):
    collections: list[CollectionResponse]
    entries: list[EntryResponse]
    attachments: list[AttachmentResponse]
    server_revision: int = Field(
        description="Opaque sync cursor: max updated_at as unix microseconds",
    )
