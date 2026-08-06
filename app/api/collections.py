from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.collection import Collection
from app.models.user import User
from app.schemas.collection import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Collection]:
    result = await db.scalars(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .where(Collection.is_deleted.is_(False))
        .order_by(Collection.sort_order, Collection.created_at)
    )
    return list(result.all())


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    body: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Collection:
    existing = await db.scalar(
        select(Collection).where(
            Collection.user_id == current_user.id,
            Collection.uuid == body.uuid,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this uuid already exists",
        )

    collection = Collection(
        user_id=current_user.id,
        uuid=body.uuid,
        encrypted_name=body.encrypted_name,
        icon=body.icon,
        color=body.color,
        parent_uuid=body.parent_uuid,
        sort_order=body.sort_order,
        revision=body.revision,
    )
    db.add(collection)
    await db.flush()
    await db.refresh(collection)
    return collection


@router.patch("/{uuid}", response_model=CollectionResponse)
async def update_collection(
    uuid: str,
    body: CollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Collection:
    collection = await db.scalar(
        select(Collection).where(
            Collection.user_id == current_user.id,
            Collection.uuid == uuid,
            Collection.is_deleted.is_(False),
        )
    )
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(collection, key, value)
    collection.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(collection)
    return collection


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    collection = await db.scalar(
        select(Collection).where(
            Collection.user_id == current_user.id,
            Collection.uuid == uuid,
            Collection.is_deleted.is_(False),
        )
    )
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    collection.is_deleted = True
    collection.revision += 1
    collection.updated_at = datetime.now(UTC)
    await db.flush()
