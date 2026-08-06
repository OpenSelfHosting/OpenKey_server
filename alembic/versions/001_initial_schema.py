"""Initial schema.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("auth_hash", sa.String(length=512), nullable=False),
        sa.Column("encrypted_vault_key", sa.String(), nullable=False),
        sa.Column("kdf_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("salt", sa.String(length=512), nullable=False),
        sa.Column("public_key", sa.String(), nullable=True),
        sa.Column("encrypted_private_key", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("encrypted_name", sa.String(), nullable=False),
        sa.Column("icon", sa.String(length=255), nullable=False),
        sa.Column("color", sa.Integer(), nullable=True),
        sa.Column("parent_uuid", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "uuid", name="uq_collections_user_uuid"),
    )
    op.create_index(op.f("ix_collections_user_id"), "collections", ["user_id"], unique=False)

    op.create_table(
        "entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("collection_uuid", sa.String(length=64), nullable=True),
        sa.Column("encrypted_payload", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "uuid", name="uq_entries_user_uuid"),
    )
    op.create_index(op.f("ix_entries_user_id"), "entries", ["user_id"], unique=False)

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("entry_uuid", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("encrypted_blob", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "uuid", name="uq_attachments_user_uuid"),
    )
    op.create_index(op.f("ix_attachments_entry_uuid"), "attachments", ["entry_uuid"], unique=False)
    op.create_index(op.f("ix_attachments_user_id"), "attachments", ["user_id"], unique=False)

    op.create_table(
        "orgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("encrypted_name", sa.String(), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_orgs_uuid"),
    )
    op.create_index(op.f("ix_orgs_owner_user_id"), "orgs", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_orgs_uuid"), "orgs", ["uuid"], unique=False)

    op.create_table(
        "shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("entry_uuid", sa.String(length=64), nullable=True),
        sa.Column("collection_uuid", sa.String(length=64), nullable=True),
        sa.Column("wrapped_item_key", sa.String(), nullable=False),
        sa.Column("encrypted_payload", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_shares_uuid"),
    )
    op.create_index(op.f("ix_shares_owner_user_id"), "shares", ["owner_user_id"], unique=False)
    op.create_index(
        op.f("ix_shares_recipient_email"),
        "shares",
        ["recipient_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shares_recipient_user_id"),
        "shares",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_shares_uuid"), "shares", ["uuid"], unique=False)

    op.create_table(
        "org_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("encrypted_name", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "uuid", name="uq_org_collections_org_uuid"),
    )
    op.create_index(op.f("ix_org_collections_org_id"), "org_collections", ["org_id"], unique=False)

    op.create_table(
        "org_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("wrapped_org_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_email", sa.String(length=320), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )
    op.create_index(
        op.f("ix_org_members_invited_email"),
        "org_members",
        ["invited_email"],
        unique=False,
    )
    op.create_index(op.f("ix_org_members_org_id"), "org_members", ["org_id"], unique=False)
    op.create_index(op.f("ix_org_members_user_id"), "org_members", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_org_members_user_id"), table_name="org_members")
    op.drop_index(op.f("ix_org_members_org_id"), table_name="org_members")
    op.drop_index(op.f("ix_org_members_invited_email"), table_name="org_members")
    op.drop_table("org_members")
    op.drop_index(op.f("ix_org_collections_org_id"), table_name="org_collections")
    op.drop_table("org_collections")
    op.drop_index(op.f("ix_shares_uuid"), table_name="shares")
    op.drop_index(op.f("ix_shares_recipient_user_id"), table_name="shares")
    op.drop_index(op.f("ix_shares_recipient_email"), table_name="shares")
    op.drop_index(op.f("ix_shares_owner_user_id"), table_name="shares")
    op.drop_table("shares")
    op.drop_index(op.f("ix_orgs_uuid"), table_name="orgs")
    op.drop_index(op.f("ix_orgs_owner_user_id"), table_name="orgs")
    op.drop_table("orgs")
    op.drop_index(op.f("ix_attachments_user_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_entry_uuid"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_index(op.f("ix_entries_user_id"), table_name="entries")
    op.drop_table("entries")
    op.drop_index(op.f("ix_collections_user_id"), table_name="collections")
    op.drop_table("collections")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
