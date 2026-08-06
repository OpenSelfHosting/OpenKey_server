"""Add org_entries for shared org vault items.

Revision ID: 003_org_entries
Revises: 002_refresh_tokens
Create Date: 2026-08-06 00:52:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_org_entries"
down_revision: Union[str, Sequence[str], None] = "002_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("collection_uuid", sa.String(length=64), nullable=True),
        sa.Column("encrypted_payload", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.UniqueConstraint("org_id", "uuid", name="uq_org_entries_org_uuid"),
    )
    op.create_index(op.f("ix_org_entries_org_id"), "org_entries", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_org_entries_org_id"), table_name="org_entries")
    op.drop_table("org_entries")
