from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EntryCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    collection_uuid: str | None = None
    encrypted_payload: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)


class EntryUpdate(BaseModel):
    collection_uuid: str | None = None
    encrypted_payload: str | None = None
    revision: int | None = Field(default=None, ge=1)
    is_deleted: bool | None = None


class EntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    collection_uuid: str | None
    encrypted_payload: str
    revision: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
