from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.collection import Collection
from app.models.entry import Entry
from app.models.user import User
from app.schemas.entry import EntryCreate, EntryResponse, EntryUpdate

router = APIRouter(prefix="/entries", tags=["entries"])


async def _require_owned_collection(
    db: AsyncSession,
    user_id: UUID,
    collection_uuid: str | None,
) -> None:
    """Reject dangling collection_uuid references (null = unfiled is allowed)."""
    if not collection_uuid:
        return
    collection = await db.scalar(
        select(Collection).where(
            Collection.user_id == user_id,
            Collection.uuid == collection_uuid,
            Collection.is_deleted.is_(False),
        )
    )
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection not found",
        )


@router.get("", response_model=list[EntryResponse])
async def list_entries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Entry]:
    result = await db.scalars(
        select(Entry)
        .where(Entry.user_id == current_user.id)
        .where(Entry.is_deleted.is_(False))
        .order_by(Entry.created_at)
    )
    return list(result.all())


@router.post(
    "",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entry(
    body: EntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Entry:
    existing = await db.scalar(
        select(Entry).where(
            Entry.user_id == current_user.id,
            Entry.uuid == body.uuid,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entry with this uuid already exists",
        )

    await _require_owned_collection(db, current_user.id, body.collection_uuid)

    entry = Entry(
        user_id=current_user.id,
        uuid=body.uuid,
        collection_uuid=body.collection_uuid,
        encrypted_payload=body.encrypted_payload,
        revision=body.revision,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.patch("/{uuid}", response_model=EntryResponse)
async def update_entry(
    uuid: str,
    body: EntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Entry:
    entry = await db.scalar(
        select(Entry).where(
            Entry.user_id == current_user.id,
            Entry.uuid == uuid,
            Entry.is_deleted.is_(False),
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    data = body.model_dump(exclude_unset=True)
    if "collection_uuid" in data:
        await _require_owned_collection(db, current_user.id, data["collection_uuid"])

    for key, value in data.items():
        setattr(entry, key, value)
    entry.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await db.scalar(
        select(Entry).where(
            Entry.user_id == current_user.id,
            Entry.uuid == uuid,
            Entry.is_deleted.is_(False),
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    entry.is_deleted = True
    entry.revision += 1
    entry.updated_at = datetime.now(UTC)
    await db.flush()
