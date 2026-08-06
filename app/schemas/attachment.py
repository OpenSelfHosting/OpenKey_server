from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MB


class AttachmentMetaResponse(BaseModel):
    """Metadata only — no ciphertext blob."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    entry_uuid: str
    filename: str
    size_bytes: int
    content_type: str | None
    revision: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class AttachmentResponse(BaseModel):
    """Full attachment including base64 ciphertext (used by /sync pull)."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    entry_uuid: str
    filename: str
    size_bytes: int
    content_type: str | None
    revision: int
    is_deleted: bool
    encrypted_blob: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_attachment(cls, attachment) -> "AttachmentResponse":
        import base64

        return cls(
            uuid=attachment.uuid,
            entry_uuid=attachment.entry_uuid,
            filename=attachment.filename,
            size_bytes=attachment.size_bytes,
            content_type=attachment.content_type,
            revision=attachment.revision,
            is_deleted=attachment.is_deleted,
            encrypted_blob=base64.b64encode(attachment.encrypted_blob).decode("ascii"),
            created_at=attachment.created_at,
            updated_at=attachment.updated_at,
        )


# Kept for OpenAPI / backwards-compatible docs references.
class AttachmentCreate(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    entry_uuid: str = Field(min_length=1, max_length=64)
    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0, le=MAX_ATTACHMENT_BYTES)
    content_type: str | None = Field(default=None, max_length=255)
    revision: int = Field(default=1, ge=1)
