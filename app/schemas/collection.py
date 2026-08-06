from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    encrypted_name: str = Field(min_length=1)
    icon: str = "material:folder"
    color: int | None = None
    parent_uuid: str | None = Field(default=None, max_length=64)
    sort_order: int = 0
    revision: int = Field(default=1, ge=1)


class CollectionUpdate(BaseModel):
    encrypted_name: str | None = None
    icon: str | None = None
    color: int | None = None
    parent_uuid: str | None = None
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
