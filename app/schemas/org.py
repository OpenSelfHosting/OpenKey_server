from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.collection import FolderId


class OrgCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    encrypted_name: str = Field(min_length=1)
    wrapped_org_key: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)


class OrgMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID | None
    role: str
    wrapped_org_key: str
    status: str
    invited_email: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class OrgMemberPublicResponse(BaseModel):
    """Member listing without per-user key material."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID | None
    role: str
    status: str
    invited_email: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class OrgMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"]


class OrgResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    encrypted_name: str
    owner_user_id: UUID
    revision: int
    created_at: datetime
    updated_at: datetime
    membership: OrgMemberResponse | None = None


class OrgInviteCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"
    wrapped_org_key: str = Field(min_length=1)


class InviteAcceptRequest(BaseModel):
    wrapped_org_key: str | None = Field(default=None, min_length=1)


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    org_uuid: str | None = None
    org_encrypted_name: str | None = None
    user_id: UUID | None
    role: str
    wrapped_org_key: str
    status: str
    invited_email: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class OrgCollectionCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    encrypted_name: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)


class OrgCollectionUpdate(BaseModel):
    encrypted_name: str | None = None
    revision: int | None = Field(default=None, ge=1)
    is_deleted: bool | None = None


class OrgCollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    encrypted_name: str
    revision: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class OrgEntryCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    collection_uuid: FolderId = None
    encrypted_payload: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)


class OrgEntryUpdate(BaseModel):
    collection_uuid: FolderId = None
    encrypted_payload: str | None = Field(default=None, min_length=1)
    revision: int | None = Field(default=None, ge=1)
    is_deleted: bool | None = None


class OrgEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    collection_uuid: str | None
    encrypted_payload: str
    revision: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
