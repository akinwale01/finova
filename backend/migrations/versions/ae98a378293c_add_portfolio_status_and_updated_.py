"""add portfolio status and updated timestamp

Revision ID: ae98a378293c
Revises: 2e7077397b44
Create Date: 2026-08-10 01:23:02.054264

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = "ae98a378293c"
down_revision: Union[str, Sequence[str], None] = "2e7077397b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Add is_active with a server-side default so existing
    # portfolio rows receive TRUE.
    op.add_column(
        "portfolios",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # Add updated_at. Existing rows receive the current
    # database timestamp through the server default.
    op.add_column(
        "portfolios",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Index active portfolios for efficient filtering.
    op.create_index(
        op.f("ix_portfolios_is_active"),
        "portfolios",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_portfolios_is_active"),
        table_name="portfolios",
    )

    op.drop_column(
        "portfolios",
        "updated_at",
    )

    op.drop_column(
        "portfolios",
        "is_active",
    )
