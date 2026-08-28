from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainValidator

from app.schemas.vault_ids import MAX_COLLECTION_ICON_CHARS, normalize_folder_id

FolderId = Annotated[
    str | None,
    PlainValidator(normalize_folder_id),
    Field(max_length=64),
]


class CollectionCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    encrypted_name: str = Field(min_length=1)
    icon: str = Field(default="material:folder", max_length=MAX_COLLECTION_ICON_CHARS)
    color: int | None = None
    parent_uuid: FolderId = None
    sort_order: int = 0
    revision: int = Field(default=1, ge=1)


class CollectionUpdate(BaseModel):
    encrypted_name: str | None = None
    icon: str | None = Field(default=None, max_length=MAX_COLLECTION_ICON_CHARS)
    color: int | None = None
    parent_uuid: FolderId = None
    sort_order: int | None = None
    revision: int | None = Field(default=None, ge=1)
    is_deleted: bool | None = None


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    encrypted_name: str
    icon: str
    color: int | None
    parent_uuid: str | None = None
    sort_order: int
    revision: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
