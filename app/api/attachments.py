import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas.attachment import MAX_ATTACHMENT_BYTES, AttachmentMetaResponse

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Read ciphertext in chunks to bound peak memory during upload.
_UPLOAD_CHUNK = 64 * 1024
_UNSAFE_FILENAME = re.compile(r'[\r\n"\\]')


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition header safe against CR/LF/quote injection."""
    cleaned = _UNSAFE_FILENAME.sub("", filename).strip()
    cleaned = "".join(c for c in cleaned if ord(c) >= 32)
    if not cleaned:
        cleaned = "attachment.bin"
    # Cap length so intermediaries cannot be flooded via oversized headers.
    cleaned = cleaned[:200]
    return f'attachment; filename="{cleaned}"'


async def _read_upload_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Attachment exceeds {max_bytes} byte limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("", response_model=list[AttachmentMetaResponse])
async def list_attachments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Attachment]:
    result = await db.scalars(
        select(Attachment)
        .where(Attachment.user_id == current_user.id)
        .where(Attachment.is_deleted.is_(False))
        .order_by(Attachment.created_at)
    )
    return list(result.all())


@router.post(
    "",
    response_model=AttachmentMetaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attachment(
    uuid: str = Form(..., min_length=1, max_length=64),
    entry_uuid: str = Form(..., min_length=1, max_length=64),
    filename: str = Form(..., min_length=1, max_length=512),
    size_bytes: int = Form(..., ge=0, le=MAX_ATTACHMENT_BYTES),
    revision: int = Form(1, ge=1),
    content_type: str | None = Form(None, max_length=255),
    file: UploadFile = File(..., description="Encrypted attachment ciphertext"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Attachment:
    """Upload ciphertext as multipart/form-data (field name: ``file``)."""
    existing = await db.scalar(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.uuid == uuid,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment with this uuid already exists",
        )

    blob = await _read_upload_bounded(file, MAX_ATTACHMENT_BYTES)
    if size_bytes != len(blob):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="size_bytes does not match uploaded file length",
        )

    resolved_content_type = content_type or file.content_type
    attachment = Attachment(
        user_id=current_user.id,
        uuid=uuid,
        entry_uuid=entry_uuid,
        filename=filename,
        size_bytes=size_bytes,
        encrypted_blob=blob,
        content_type=resolved_content_type,
        revision=revision,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    return attachment


@router.get("/{uuid}", response_model=AttachmentMetaResponse)
async def get_attachment(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Attachment:
    """Return attachment metadata (ciphertext via ``GET …/content``)."""
    attachment = await db.scalar(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.uuid == uuid,
            Attachment.is_deleted.is_(False),
        )
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )
    return attachment


@router.get("/{uuid}/content")
async def download_attachment_content(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream raw encrypted bytes (application/octet-stream)."""
    attachment = await db.scalar(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.uuid == uuid,
            Attachment.is_deleted.is_(False),
        )
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    blob = attachment.encrypted_blob

    async def _iter():
        # Yield in chunks so large blobs are not held as one Response body copy
        # beyond the ORM-loaded buffer already in memory.
        view = memoryview(blob)
        step = 64 * 1024
        for start in range(0, len(view), step):
            yield bytes(view[start : start + step])

    headers = {
        "Content-Length": str(len(blob)),
        "Content-Disposition": _content_disposition(attachment.filename),
        "X-OpenKey-Size-Bytes": str(attachment.size_bytes),
        "X-OpenKey-Entry-Uuid": attachment.entry_uuid,
    }
    return StreamingResponse(
        _iter(),
        media_type="application/octet-stream",
        headers=headers,
    )


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    attachment = await db.scalar(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.uuid == uuid,
            Attachment.is_deleted.is_(False),
        )
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    attachment.is_deleted = True
    attachment.revision += 1
    attachment.updated_at = datetime.now(UTC)
    await db.flush()
