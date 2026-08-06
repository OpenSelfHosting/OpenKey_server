import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    auth_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    encrypted_vault_key: Mapped[str] = mapped_column(String, nullable=False)
    kdf_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    salt: Mapped[str] = mapped_column(String(512), nullable=False)
    public_key: Mapped[str | None] = mapped_column(String, nullable=True)
    encrypted_private_key: Mapped[str | None] = mapped_column(String, nullable=True)
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

    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    entries = relationship("Entry", back_populates="user", cascade="all, delete-orphan")
    attachments = relationship(
        "Attachment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    owned_orgs = relationship(
        "Org",
        back_populates="owner",
        foreign_keys="Org.owner_user_id",
        cascade="all, delete-orphan",
    )
    org_memberships = relationship("OrgMember", back_populates="user")
    owned_shares = relationship(
        "Share",
        back_populates="owner",
        foreign_keys="Share.owner_user_id",
        cascade="all, delete-orphan",
    )
    received_shares = relationship(
        "Share",
        back_populates="recipient",
        foreign_keys="Share.recipient_user_id",
    )
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
