import uuid
from datetime import datetime
from uuid import UUID as Uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (
        UniqueConstraint("uuid", name="uq_shares_uuid"),
    )

    id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Client-facing string id — avoid `uuid.UUID` annotations after this field
    # (shadows the stdlib module under Python ≤3.13).
    uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[Uuid] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_user_id: Mapped[Uuid | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    entry_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collection_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wrapped_item_key: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_payload: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
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

    owner = relationship(
        "User",
        back_populates="owned_shares",
        foreign_keys=[owner_user_id],
    )
    recipient = relationship(
        "User",
        back_populates="received_shares",
        foreign_keys=[recipient_user_id],
    )
