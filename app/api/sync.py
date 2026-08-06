import base64
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.collection import Collection
from app.models.entry import Entry
from app.models.user import User
from app.schemas.attachment import MAX_ATTACHMENT_BYTES, AttachmentResponse
from app.schemas.sync import SyncRequest, SyncResponse

router = APIRouter(prefix="/sync", tags=["sync"])

# Epoch used when since_revision is 0 (full pull).
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _since_to_datetime(since_revision: int) -> datetime:
    """Map sync cursor (unix microseconds) to a timezone-aware datetime."""
    if since_revision <= 0:
        return _EPOCH
    return datetime.fromtimestamp(since_revision / 1_000_000, tz=UTC)


def _datetime_to_revision(value: datetime | None) -> int:
    """Map updated_at to the opaque sync cursor (unix microseconds)."""
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1_000_000)


def _upsert_collection_row(
    existing: Collection | None,
    user_id: UUID,
    item,
    now: datetime,
) -> tuple[Collection | None, Collection | None]:
    """Apply LWW upsert in-memory.

    Returns ``(new_row_or_None, conflict_winner_or_None)``.
    """
    if existing is None:
        return (
            Collection(
                user_id=user_id,
                uuid=item.uuid,
                encrypted_name=item.encrypted_name,
                icon=item.icon,
                color=item.color,
                parent_uuid=item.parent_uuid,
                sort_order=item.sort_order,
                revision=item.revision,
                is_deleted=item.is_deleted,
            ),
            None,
        )

    if item.revision > existing.revision:
        existing.encrypted_name = item.encrypted_name
        existing.icon = item.icon
        existing.color = item.color
        existing.parent_uuid = item.parent_uuid
        existing.sort_order = item.sort_order
        existing.revision = item.revision
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    if item.revision == existing.revision:
        # Identical equal-revision push is a no-op (avoid updated_at churn).
        unchanged = (
            existing.encrypted_name == item.encrypted_name
            and existing.icon == item.icon
            and existing.color == item.color
            and existing.parent_uuid == item.parent_uuid
            and existing.sort_order == item.sort_order
            and existing.is_deleted == item.is_deleted
        )
        if unchanged:
            return None, None
        existing.encrypted_name = item.encrypted_name
        existing.icon = item.icon
        existing.color = item.color
        existing.parent_uuid = item.parent_uuid
        existing.sort_order = item.sort_order
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    # Stale push lost LWW — echo the winner so the client learns without a full pull.
    return None, existing


def _upsert_entry_row(
    existing: Entry | None,
    user_id: UUID,
    item,
    now: datetime,
) -> tuple[Entry | None, Entry | None]:
    if existing is None:
        return (
            Entry(
                user_id=user_id,
                uuid=item.uuid,
                collection_uuid=item.collection_uuid,
                encrypted_payload=item.encrypted_payload,
                revision=item.revision,
                is_deleted=item.is_deleted,
            ),
            None,
        )

    if item.revision > existing.revision:
        existing.collection_uuid = item.collection_uuid
        existing.encrypted_payload = item.encrypted_payload
        existing.revision = item.revision
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    if item.revision == existing.revision:
        unchanged = (
            existing.collection_uuid == item.collection_uuid
            and existing.encrypted_payload == item.encrypted_payload
            and existing.is_deleted == item.is_deleted
        )
        if unchanged:
            return None, None
        existing.collection_uuid = item.collection_uuid
        existing.encrypted_payload = item.encrypted_payload
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    return None, existing


def _upsert_attachment_row(
    existing: Attachment | None,
    user_id: UUID,
    item,
    now: datetime,
) -> tuple[Attachment | None, Attachment | None]:
    try:
        blob = base64.b64decode(item.encrypted_blob, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid base64 for attachment {item.uuid}",
        ) from exc

    if len(blob) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Attachment {item.uuid} exceeds {MAX_ATTACHMENT_BYTES} byte limit",
        )

    size_bytes = item.size_bytes if item.size_bytes is not None else len(blob)
    if size_bytes != len(blob):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"size_bytes mismatch for attachment {item.uuid}",
        )

    if existing is None:
        return (
            Attachment(
                user_id=user_id,
                uuid=item.uuid,
                entry_uuid=item.entry_uuid,
                filename=item.filename,
                size_bytes=size_bytes,
                encrypted_blob=blob,
                content_type=item.content_type,
                revision=item.revision,
                is_deleted=item.is_deleted,
            ),
            None,
        )

    if item.revision > existing.revision:
        existing.entry_uuid = item.entry_uuid
        existing.filename = item.filename
        existing.size_bytes = size_bytes
        existing.encrypted_blob = blob
        existing.content_type = item.content_type
        existing.revision = item.revision
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    if item.revision == existing.revision:
        unchanged = (
            existing.entry_uuid == item.entry_uuid
            and existing.filename == item.filename
            and existing.size_bytes == size_bytes
            and existing.encrypted_blob == blob
            and existing.content_type == item.content_type
            and existing.is_deleted == item.is_deleted
        )
        if unchanged:
            return None, None
        existing.entry_uuid = item.entry_uuid
        existing.filename = item.filename
        existing.size_bytes = size_bytes
        existing.encrypted_blob = blob
        existing.content_type = item.content_type
        existing.is_deleted = item.is_deleted
        existing.updated_at = now
        return None, None

    return None, existing


def _merge_by_uuid(primary: list, extras: list) -> list:
    seen = {row.uuid for row in primary}
    out = list(primary)
    for row in extras:
        if row.uuid not in seen:
            out.append(row)
            seen.add(row.uuid)
    return out


@router.post("", response_model=SyncResponse)
async def sync_vault(
    body: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncResponse:
    """Push local ciphertext (LWW by revision) and pull rows with updated_at > since_revision.

    ``since_revision`` / ``server_revision`` are unix microseconds of ``updated_at``.
    Pass ``0`` for a full pull. Per-item ``revision`` is only for conflict resolution.

    When a pushed item loses LWW, the winning server row is included in the
    response even if its ``updated_at`` is not newer than ``since_revision``.
    """
    since_dt = _since_to_datetime(body.since_revision or 0)
    now = datetime.now(UTC)
    conflict_collections: list[Collection] = []
    conflict_entries: list[Entry] = []
    conflict_attachments: list[Attachment] = []

    push_collections = body.collections or []
    push_entries = body.entries or []
    push_attachments = body.attachments or []

    # Prefetch existing rows in bulk (avoids N+1 selects on large sync pushes).
    existing_collections: dict[str, Collection] = {}
    if push_collections:
        uuids = [item.uuid for item in push_collections]
        rows = (
            await db.scalars(
                select(Collection).where(
                    Collection.user_id == current_user.id,
                    Collection.uuid.in_(uuids),
                )
            )
        ).all()
        existing_collections = {row.uuid: row for row in rows}

    for item in push_collections:
        new_row, lost = _upsert_collection_row(
            existing_collections.get(item.uuid),
            current_user.id,
            item,
            now,
        )
        if new_row is not None:
            db.add(new_row)
            existing_collections[item.uuid] = new_row
        if lost is not None:
            conflict_collections.append(lost)

    existing_entries: dict[str, Entry] = {}
    if push_entries:
        uuids = [item.uuid for item in push_entries]
        rows = (
            await db.scalars(
                select(Entry).where(
                    Entry.user_id == current_user.id,
                    Entry.uuid.in_(uuids),
                )
            )
        ).all()
        existing_entries = {row.uuid: row for row in rows}

    for item in push_entries:
        new_row, lost = _upsert_entry_row(
            existing_entries.get(item.uuid),
            current_user.id,
            item,
            now,
        )
        if new_row is not None:
            db.add(new_row)
            existing_entries[item.uuid] = new_row
        if lost is not None:
            conflict_entries.append(lost)

    existing_attachments: dict[str, Attachment] = {}
    if push_attachments:
        uuids = [item.uuid for item in push_attachments]
        rows = (
            await db.scalars(
                select(Attachment).where(
                    Attachment.user_id == current_user.id,
                    Attachment.uuid.in_(uuids),
                )
            )
        ).all()
        existing_attachments = {row.uuid: row for row in rows}

    for item in push_attachments:
        new_row, lost = _upsert_attachment_row(
            existing_attachments.get(item.uuid),
            current_user.id,
            item,
            now,
        )
        if new_row is not None:
            db.add(new_row)
            existing_attachments[item.uuid] = new_row
        if lost is not None:
            conflict_attachments.append(lost)

    await db.flush()

    collections = list(
        (
            await db.scalars(
                select(Collection).where(
                    Collection.user_id == current_user.id,
                    Collection.updated_at > since_dt,
                )
            )
        ).all()
    )
    entries = list(
        (
            await db.scalars(
                select(Entry).where(
                    Entry.user_id == current_user.id,
                    Entry.updated_at > since_dt,
                )
            )
        ).all()
    )
    attachment_rows = list(
        (
            await db.scalars(
                select(Attachment).where(
                    Attachment.user_id == current_user.id,
                    Attachment.updated_at > since_dt,
                )
            )
        ).all()
    )

    collections = _merge_by_uuid(collections, conflict_collections)
    entries = _merge_by_uuid(entries, conflict_entries)
    attachment_rows = _merge_by_uuid(attachment_rows, conflict_attachments)
    attachments = [
        AttachmentResponse.from_orm_attachment(row) for row in attachment_rows
    ]

    max_collection_at = await db.scalar(
        select(func.max(Collection.updated_at)).where(
            Collection.user_id == current_user.id
        )
    )
    max_entry_at = await db.scalar(
        select(func.max(Entry.updated_at)).where(Entry.user_id == current_user.id)
    )
    max_attachment_at = await db.scalar(
        select(func.max(Attachment.updated_at)).where(
            Attachment.user_id == current_user.id
        )
    )
    server_revision = max(
        _datetime_to_revision(max_collection_at),
        _datetime_to_revision(max_entry_at),
        _datetime_to_revision(max_attachment_at),
    )

    return SyncResponse(
        collections=collections,
        entries=entries,
        attachments=attachments,
        server_revision=server_revision,
    )
