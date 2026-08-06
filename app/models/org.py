import uuid
from datetime import datetime
from uuid import UUID as Uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = (
        UniqueConstraint("uuid", name="uq_orgs_uuid"),
    )

    id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Client-facing string id — do not name type refs `uuid.UUID` after this field
    # (shadows the stdlib module under Python ≤3.13 annotation evaluation).
    uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    encrypted_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_user_id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner = relationship("User", back_populates="owned_orgs", foreign_keys=[owner_user_id])
    members = relationship(
        "OrgMember",
        back_populates="org",
        cascade="all, delete-orphan",
    )
    collections = relationship(
        "OrgCollection",
        back_populates="org",
        cascade="all, delete-orphan",
    )
    entries = relationship(
        "OrgEntry",
        back_populates="org",
        cascade="all, delete-orphan",
    )


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )

    id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Uuid | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    wrapped_org_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="invited")
    invited_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    org = relationship("Org", back_populates="members")
    user = relationship("User", back_populates="org_memberships")


class OrgCollection(Base):
    __tablename__ = "org_collections"
    __table_args__ = (
        UniqueConstraint("org_id", "uuid", name="uq_org_collections_org_uuid"),
    )

    id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    org = relationship("Org", back_populates="collections")


class OrgEntry(Base):
    """Shared vault item ciphertext encrypted with the org key (zero-knowledge)."""

    __tablename__ = "org_entries"
    __table_args__ = (
        UniqueConstraint("org_id", "uuid", name="uq_org_entries_org_uuid"),
    )

    id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    # Client uuid of an OrgCollection (not a FK — collections are soft-deleted).
    collection_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encrypted_payload: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    org = relationship("Org", back_populates="entries")
