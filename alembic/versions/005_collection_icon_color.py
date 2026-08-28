"""Widen collection icon/color for app 1.0.6 custom icons and ARGB colors.

Revision ID: 005_collection_icon_color
Revises: 004_sync_updated_at_indexes
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_collection_icon_color"
down_revision: Union[str, Sequence[str], None] = "004_sync_updated_at_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "collections",
        "icon",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
        existing_server_default=None,
    )
    op.alter_column(
        "collections",
        "color",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "collections",
        "color",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "collections",
        "icon",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
