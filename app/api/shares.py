from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.share import Share
from app.models.user import User
from app.schemas.share import ShareCreate, ShareResponse

router = APIRouter(prefix="/shares", tags=["shares"])


@router.post(
    "",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    body: ShareCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Share:
    existing = await db.scalar(select(Share).where(Share.uuid == body.uuid))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Share with this uuid already exists",
        )

    recipient_user_id = body.recipient_user_id
    recipient_email = body.recipient_email.lower() if body.recipient_email else None

    if recipient_user_id is not None:
        recipient = await db.scalar(select(User).where(User.id == recipient_user_id))
        if recipient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient user not found",
            )
        recipient_email = recipient.email
    elif recipient_email is not None:
        recipient = await db.scalar(select(User).where(User.email == recipient_email))
        if recipient is not None:
            recipient_user_id = recipient.id

    if recipient_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share with yourself",
        )

    share = Share(
        uuid=body.uuid,
        owner_user_id=current_user.id,
        recipient_user_id=recipient_user_id,
        recipient_email=recipient_email,
        entry_uuid=body.entry_uuid,
        collection_uuid=body.collection_uuid,
        wrapped_item_key=body.wrapped_item_key,
        encrypted_payload=body.encrypted_payload,
        status="pending",
        revision=body.revision,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return share


@router.get("", response_model=list[ShareResponse])
async def list_shares(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Share]:
    result = await db.scalars(
        select(Share)
        .where(
            or_(
                Share.owner_user_id == current_user.id,
                Share.recipient_user_id == current_user.id,
                Share.recipient_email == current_user.email,
            ),
            Share.status != "revoked",
        )
        .order_by(Share.created_at)
    )
    return list(result.all())


@router.post("/{uuid}/accept", response_model=ShareResponse)
async def accept_share(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Share:
    share = await db.scalar(select(Share).where(Share.uuid == uuid))
    if share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found",
        )
    if share.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share is not pending",
        )

    is_recipient = (
        share.recipient_user_id == current_user.id
        or share.recipient_email == current_user.email
    )
    if not is_recipient:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Share is not for this user",
        )

    if not share.encrypted_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share has no snapshot payload to import",
        )

    share.recipient_user_id = current_user.id
    share.recipient_email = current_user.email
    share.status = "accepted"
    share.revision += 1
    share.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(share)
    return share


@router.post("/{uuid}/revoke", response_model=ShareResponse)
async def revoke_share(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Share:
    """Revoke a pending or accepted share. Owner only.

    Shares are point-in-time snapshots: revoking stops further accept of a
    pending share. An already-accepted import in the recipient's vault is
    independent and is not deleted server-side.
    """
    share = await db.scalar(select(Share).where(Share.uuid == uuid))
    if share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found",
        )
    if share.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the share owner can revoke",
        )
    if share.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share is already revoked",
        )
    if share.status not in ("pending", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share cannot be revoked",
        )

    share.status = "revoked"
    share.revision += 1
    share.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(share)
    return share
