from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ShareCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    recipient_user_id: UUID | None = None
    recipient_email: EmailStr | None = None
    entry_uuid: str | None = Field(default=None, max_length=64)
    collection_uuid: str | None = Field(default=None, max_length=64)
    wrapped_item_key: str = Field(min_length=1)
    encrypted_payload: str | None = None
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def require_recipient_and_target(self) -> "ShareCreate":
        if self.recipient_user_id is None and self.recipient_email is None:
            raise ValueError("Either recipient_user_id or recipient_email is required")
        if self.entry_uuid is None and self.collection_uuid is None:
            raise ValueError("Either entry_uuid or collection_uuid is required")
        # Entry shares are snapshots: the ciphertext payload is frozen at
        # create time and is not kept in sync with the owner's original item.
        if self.entry_uuid is not None and (
            self.encrypted_payload is None or not self.encrypted_payload.strip()
        ):
            raise ValueError(
                "encrypted_payload is required for entry shares (snapshot)"
            )
        return self


class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    owner_user_id: UUID
    recipient_user_id: UUID | None
    recipient_email: str | None
    entry_uuid: str | None
    collection_uuid: str | None
    wrapped_item_key: str
    encrypted_payload: str | None
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime
