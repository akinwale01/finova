"""add asset metadata status and timestamps

Revision ID: 2da3fcae3b62
Revises: ae98a378293c
Create Date: 2026-08-10 11:36:57.367389

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2da3fcae3b62"
down_revision: Union[str, Sequence[str], None] = "ae98a378293c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "assets",
        sa.Column(
            "market",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "quote_currency",
            sa.String(length=10),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "external_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    # Existing Asset rows receive TRUE.
    op.add_column(
        "assets",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        op.f("ix_assets_external_id"),
        "assets",
        ["external_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_is_active"),
        "assets",
        ["is_active"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_market"),
        "assets",
        ["market"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_assets_market"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_is_active"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_external_id"),
        table_name="assets",
    )

    op.drop_column(
        "assets",
        "updated_at",
    )

    op.drop_column(
        "assets",
        "created_at",
    )

    op.drop_column(
        "assets",
        "is_active",
    )

    op.drop_column(
        "assets",
        "external_id",
    )

    op.drop_column(
        "assets",
        "quote_currency",
    )

    op.drop_column(
        "assets",
        "market",
    )
    # ### end Alembic commands ###
