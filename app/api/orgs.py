from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.org import Org, OrgCollection, OrgEntry, OrgMember
from app.models.user import User
from app.schemas.org import (
    InviteAcceptRequest,
    InviteResponse,
    OrgCollectionCreate,
    OrgCollectionResponse,
    OrgCollectionUpdate,
    OrgCreate,
    OrgEntryCreate,
    OrgEntryResponse,
    OrgEntryUpdate,
    OrgInviteCreate,
    OrgMemberPublicResponse,
    OrgMemberResponse,
    OrgMemberRoleUpdate,
    OrgResponse,
)

router = APIRouter(tags=["orgs"])


def _org_response(org: Org, membership: OrgMember | None) -> OrgResponse:
    return OrgResponse(
        uuid=org.uuid,
        encrypted_name=org.encrypted_name,
        owner_user_id=org.owner_user_id,
        revision=org.revision,
        created_at=org.created_at,
        updated_at=org.updated_at,
        membership=OrgMemberResponse.model_validate(membership) if membership else None,
    )


def _invite_response(member: OrgMember, org: Org | None = None) -> InviteResponse:
    org = org or member.org
    return InviteResponse(
        id=member.id,
        org_id=member.org_id,
        org_uuid=org.uuid if org else None,
        org_encrypted_name=org.encrypted_name if org else None,
        user_id=member.user_id,
        role=member.role,
        wrapped_org_key=member.wrapped_org_key,
        status=member.status,
        invited_email=member.invited_email,
        revision=member.revision,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


async def _get_org_or_404(db: AsyncSession, uuid: str) -> Org:
    org = await db.scalar(select(Org).where(Org.uuid == uuid))
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Org not found",
        )
    return org


async def _active_membership(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
) -> OrgMember | None:
    return await db.scalar(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user_id,
            OrgMember.status == "active",
        )
    )


async def _require_active_member(
    db: AsyncSession,
    org: Org,
    user: User,
) -> OrgMember:
    membership = await _active_membership(db, org.id, user.id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an active org member",
        )
    return membership


async def _require_admin(
    db: AsyncSession,
    org: Org,
    user: User,
) -> OrgMember:
    membership = await _require_active_member(db, org, user)
    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org owners/admins can perform this action",
        )
    return membership


def _touch_member(member: OrgMember) -> None:
    member.revision += 1
    member.updated_at = datetime.now(UTC)


@router.post(
    "/orgs",
    response_model=OrgResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org(
    body: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgResponse:
    existing = await db.scalar(select(Org).where(Org.uuid == body.uuid))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Org with this uuid already exists",
        )

    org = Org(
        uuid=body.uuid,
        encrypted_name=body.encrypted_name,
        owner_user_id=current_user.id,
        revision=body.revision,
    )
    db.add(org)
    await db.flush()

    membership = OrgMember(
        org_id=org.id,
        user_id=current_user.id,
        role="owner",
        wrapped_org_key=body.wrapped_org_key,
        status="active",
        invited_email=current_user.email,
        revision=1,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(org)
    await db.refresh(membership)
    return _org_response(org, membership)


@router.get("/orgs", response_model=list[OrgResponse])
async def list_orgs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrgResponse]:
    memberships = list(
        (
            await db.scalars(
                select(OrgMember)
                .where(
                    OrgMember.user_id == current_user.id,
                    OrgMember.status == "active",
                )
                .options(selectinload(OrgMember.org))
            )
        ).all()
    )
    return [_org_response(m.org, m) for m in memberships]


@router.post(
    "/orgs/{uuid}/invites",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_to_org(
    uuid: str,
    body: OrgInviteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    org = await _get_org_or_404(db, uuid)
    await _require_admin(db, org, current_user)

    email = body.email.lower()
    if email == current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot invite yourself",
        )

    recipient = await db.scalar(select(User).where(User.email == email))

    conditions = [OrgMember.invited_email == email]
    if recipient is not None:
        conditions.append(OrgMember.user_id == recipient.id)

    existing = await db.scalar(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            or_(*conditions),
        )
    )
    if existing is not None and existing.status != "revoked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already invited or a member",
        )

    if existing is not None:
        existing.role = body.role
        existing.wrapped_org_key = body.wrapped_org_key
        existing.status = "invited"
        existing.invited_email = email
        existing.user_id = recipient.id if recipient else None
        _touch_member(existing)
        membership = existing
    else:
        membership = OrgMember(
            org_id=org.id,
            user_id=recipient.id if recipient else None,
            role=body.role,
            wrapped_org_key=body.wrapped_org_key,
            status="invited",
            invited_email=email,
            revision=1,
        )
        db.add(membership)

    await db.flush()
    await db.refresh(membership)
    return _invite_response(membership, org)


@router.get("/invites/pending", response_model=list[InviteResponse])
async def list_pending_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InviteResponse]:
    members = list(
        (
            await db.scalars(
                select(OrgMember)
                .where(
                    OrgMember.status == "invited",
                    OrgMember.invited_email == current_user.email,
                )
                .options(selectinload(OrgMember.org))
                .order_by(OrgMember.created_at)
            )
        ).all()
    )
    return [_invite_response(m) for m in members]


@router.post("/invites/{invite_id}/accept", response_model=InviteResponse)
async def accept_invite(
    invite_id: UUID,
    body: InviteAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    membership = await db.scalar(
        select(OrgMember)
        .where(OrgMember.id == invite_id)
        .options(selectinload(OrgMember.org))
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )
    if membership.status != "invited":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is not pending",
        )
    if membership.invited_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invite is not for this user",
        )

    membership.user_id = current_user.id
    membership.status = "active"
    if body.wrapped_org_key is not None:
        membership.wrapped_org_key = body.wrapped_org_key
    _touch_member(membership)

    await db.flush()
    await db.refresh(membership)
    return _invite_response(membership)


@router.get(
    "/orgs/{uuid}/members",
    response_model=list[OrgMemberPublicResponse],
)
async def list_members(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrgMember]:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    result = await db.scalars(
        select(OrgMember)
        .where(
            OrgMember.org_id == org.id,
            OrgMember.status.in_(("active", "invited")),
        )
        .order_by(OrgMember.created_at)
    )
    return list(result.all())


@router.patch(
    "/orgs/{uuid}/members/{member_id}",
    response_model=OrgMemberPublicResponse,
)
async def update_member_role(
    uuid: str,
    member_id: UUID,
    body: OrgMemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgMember:
    org = await _get_org_or_404(db, uuid)
    actor = await _require_admin(db, org, current_user)

    member = await db.scalar(
        select(OrgMember).where(
            OrgMember.id == member_id,
            OrgMember.org_id == org.id,
        )
    )
    if member is None or member.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    if member.status != "active" and member.status != "invited":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change role for this membership",
        )
    if member.role == "owner" or member.user_id == org.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the org owner's role",
        )
    if member.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )
    if actor.role == "admin" and member.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot change other admins",
        )
    if actor.role == "admin" and body.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can promote admins",
        )

    member.role = body.role
    _touch_member(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.delete(
    "/orgs/{uuid}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    uuid: str,
    member_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an active member or revoke a pending invite."""
    org = await _get_org_or_404(db, uuid)
    actor = await _require_admin(db, org, current_user)

    member = await db.scalar(
        select(OrgMember).where(
            OrgMember.id == member_id,
            OrgMember.org_id == org.id,
        )
    )
    if member is None or member.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    if member.role == "owner" or member.user_id == org.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the org owner",
        )
    if member.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use leave to remove yourself",
        )
    if actor.role == "admin" and member.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove other admins",
        )

    member.status = "revoked"
    _touch_member(member)
    await db.flush()


@router.post(
    "/orgs/{uuid}/invites/{invite_id}/revoke",
    response_model=InviteResponse,
)
async def revoke_invite(
    uuid: str,
    invite_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    org = await _get_org_or_404(db, uuid)
    await _require_admin(db, org, current_user)

    membership = await db.scalar(
        select(OrgMember)
        .where(
            OrgMember.id == invite_id,
            OrgMember.org_id == org.id,
        )
        .options(selectinload(OrgMember.org))
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )
    if membership.status != "invited":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is not pending",
        )

    membership.status = "revoked"
    _touch_member(membership)
    await db.flush()
    await db.refresh(membership)
    return _invite_response(membership, org)


@router.post("/orgs/{uuid}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_org(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(db, uuid)
    membership = await _require_active_member(db, org, current_user)

    if membership.role == "owner" or current_user.id == org.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot leave the organization",
        )

    membership.status = "revoked"
    _touch_member(membership)
    await db.flush()


@router.get(
    "/orgs/{uuid}/collections",
    response_model=list[OrgCollectionResponse],
)
async def list_org_collections(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrgCollection]:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    result = await db.scalars(
        select(OrgCollection)
        .where(
            OrgCollection.org_id == org.id,
            OrgCollection.is_deleted.is_(False),
        )
        .order_by(OrgCollection.created_at)
    )
    return list(result.all())


@router.post(
    "/orgs/{uuid}/collections",
    response_model=OrgCollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_collection(
    uuid: str,
    body: OrgCollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgCollection:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    existing = await db.scalar(
        select(OrgCollection).where(
            OrgCollection.org_id == org.id,
            OrgCollection.uuid == body.uuid,
        )
    )
    if existing is not None and not existing.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this uuid already exists",
        )

    if existing is not None:
        existing.encrypted_name = body.encrypted_name
        existing.revision = body.revision
        existing.is_deleted = False
        existing.updated_at = datetime.now(UTC)
        collection = existing
    else:
        collection = OrgCollection(
            org_id=org.id,
            uuid=body.uuid,
            encrypted_name=body.encrypted_name,
            revision=body.revision,
            is_deleted=False,
        )
        db.add(collection)

    await db.flush()
    await db.refresh(collection)
    return collection


@router.patch(
    "/orgs/{uuid}/collections/{collection_uuid}",
    response_model=OrgCollectionResponse,
)
async def update_org_collection(
    uuid: str,
    collection_uuid: str,
    body: OrgCollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgCollection:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    collection = await db.scalar(
        select(OrgCollection).where(
            OrgCollection.org_id == org.id,
            OrgCollection.uuid == collection_uuid,
            OrgCollection.is_deleted.is_(False),
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


@router.delete(
    "/orgs/{uuid}/collections/{collection_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_org_collection(
    uuid: str,
    collection_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(db, uuid)
    await _require_admin(db, org, current_user)

    collection = await db.scalar(
        select(OrgCollection).where(
            OrgCollection.org_id == org.id,
            OrgCollection.uuid == collection_uuid,
            OrgCollection.is_deleted.is_(False),
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


@router.get(
    "/orgs/{uuid}/entries",
    response_model=list[OrgEntryResponse],
)
async def list_org_entries(
    uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrgEntry]:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    result = await db.scalars(
        select(OrgEntry)
        .where(
            OrgEntry.org_id == org.id,
            OrgEntry.is_deleted.is_(False),
        )
        .order_by(OrgEntry.created_at)
    )
    return list(result.all())


@router.post(
    "/orgs/{uuid}/entries",
    response_model=OrgEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_entry(
    uuid: str,
    body: OrgEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgEntry:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    if body.collection_uuid:
        collection = await db.scalar(
            select(OrgCollection).where(
                OrgCollection.org_id == org.id,
                OrgCollection.uuid == body.collection_uuid,
                OrgCollection.is_deleted.is_(False),
            )
        )
        if collection is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Org collection not found",
            )

    existing = await db.scalar(
        select(OrgEntry).where(
            OrgEntry.org_id == org.id,
            OrgEntry.uuid == body.uuid,
        )
    )
    if existing is not None and not existing.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entry with this uuid already exists",
        )

    if existing is not None:
        existing.collection_uuid = body.collection_uuid
        existing.encrypted_payload = body.encrypted_payload
        existing.revision = body.revision
        existing.is_deleted = False
        existing.updated_at = datetime.now(UTC)
        entry = existing
    else:
        entry = OrgEntry(
            org_id=org.id,
            uuid=body.uuid,
            collection_uuid=body.collection_uuid,
            encrypted_payload=body.encrypted_payload,
            revision=body.revision,
            is_deleted=False,
        )
        db.add(entry)

    await db.flush()
    await db.refresh(entry)
    return entry


@router.patch(
    "/orgs/{uuid}/entries/{entry_uuid}",
    response_model=OrgEntryResponse,
)
async def update_org_entry(
    uuid: str,
    entry_uuid: str,
    body: OrgEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgEntry:
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    entry = await db.scalar(
        select(OrgEntry).where(
            OrgEntry.org_id == org.id,
            OrgEntry.uuid == entry_uuid,
            OrgEntry.is_deleted.is_(False),
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    data = body.model_dump(exclude_unset=True)
    if "collection_uuid" in data and data["collection_uuid"]:
        collection = await db.scalar(
            select(OrgCollection).where(
                OrgCollection.org_id == org.id,
                OrgCollection.uuid == data["collection_uuid"],
                OrgCollection.is_deleted.is_(False),
            )
        )
        if collection is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Org collection not found",
            )

    for key, value in data.items():
        setattr(entry, key, value)
    entry.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete(
    "/orgs/{uuid}/entries/{entry_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_org_entry(
    uuid: str,
    entry_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a shared org entry. Any active member may delete."""
    org = await _get_org_or_404(db, uuid)
    await _require_active_member(db, org, current_user)

    entry = await db.scalar(
        select(OrgEntry).where(
            OrgEntry.org_id == org.id,
            OrgEntry.uuid == entry_uuid,
            OrgEntry.is_deleted.is_(False),
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
