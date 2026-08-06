"""Add composite indexes for sync pull by user_id + updated_at.

Revision ID: 004_sync_updated_at_indexes
Revises: 003_org_entries
Create Date: 2026-08-06 06:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_sync_updated_at_indexes"
down_revision: Union[str, Sequence[str], None] = "003_org_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_collections_user_updated_at",
        "collections",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_entries_user_updated_at",
        "entries",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_attachments_user_updated_at",
        "attachments",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_user_updated_at", table_name="attachments")
    op.drop_index("ix_entries_user_updated_at", table_name="entries")
    op.drop_index("ix_collections_user_updated_at", table_name="collections")
