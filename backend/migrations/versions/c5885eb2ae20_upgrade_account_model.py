"""upgrade account model

Revision ID: c5885eb2ae20
Revises: 5d1403c87c0d
Create Date: 2026-08-11 15:30:01.561038

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = "c5885eb2ae20"
down_revision: Union[str, Sequence[str], None] = "5d1403c87c0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade the accounts table to the production-ready model."""

    # ---------------------------------------------------------
    # RENAME EXISTING COLUMN
    # ---------------------------------------------------------
    #
    # The model changed:
    #
    #     balance_updated_at
    #
    # to:
    #
    #     last_synced_at
    #
    # This is a rename, NOT a delete/recreate operation.
    # Renaming preserves any existing synchronization timestamps.
    #
    op.alter_column(
        "accounts",
        "balance_updated_at",
        new_column_name="last_synced_at",
    )

    # ---------------------------------------------------------
    # EXTERNAL PROVIDER INFORMATION
    # ---------------------------------------------------------

    op.add_column(
        "accounts",
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "accounts",
        sa.Column(
            "external_account_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # BALANCE PRECISION
    # ---------------------------------------------------------
    #
    # Increase precision from:
    #
    #     NUMERIC(20, 8)
    #
    # to:
    #
    #     NUMERIC(30, 18)
    #
    # This is important because accounts can represent
    # cryptocurrencies and other assets requiring greater
    # decimal precision.
    #

    op.alter_column(
        "accounts",
        "balance",
        existing_type=sa.NUMERIC(
            precision=20,
            scale=8,
        ),
        type_=sa.Numeric(
            precision=30,
            scale=18,
        ),
        existing_nullable=False,
    )

    # ---------------------------------------------------------
    # INDEXES
    # ---------------------------------------------------------

    op.create_index(
        "ix_accounts_external_account_id",
        "accounts",
        ["external_account_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_accounts_is_active"),
        "accounts",
        ["is_active"],
        unique=False,
    )

    op.create_index(
        "ix_accounts_user_active",
        "accounts",
        ["user_id", "is_active"],
        unique=False,
    )

    op.create_index(
        "ix_accounts_user_type",
        "accounts",
        ["user_id", "account_type"],
        unique=False,
    )

    # ---------------------------------------------------------
    # DATA INTEGRITY
    # ---------------------------------------------------------
    #
    # An account balance cannot be negative.
    #
    op.create_check_constraint(
        "ck_accounts_balance_non_negative",
        "accounts",
        "balance >= 0",
    )


def downgrade() -> None:
    """Downgrade the accounts table to the previous schema."""

    # ---------------------------------------------------------
    # REMOVE DATA INTEGRITY CONSTRAINT
    # ---------------------------------------------------------

    op.drop_constraint(
        "ck_accounts_balance_non_negative",
        "accounts",
        type_="check",
    )

    # ---------------------------------------------------------
    # REMOVE INDEXES
    # ---------------------------------------------------------

    op.drop_index(
        "ix_accounts_user_type",
        table_name="accounts",
    )

    op.drop_index(
        "ix_accounts_user_active",
        table_name="accounts",
    )

    op.drop_index(
        op.f("ix_accounts_is_active"),
        table_name="accounts",
    )

    op.drop_index(
        "ix_accounts_external_account_id",
        table_name="accounts",
    )

    # ---------------------------------------------------------
    # RESTORE ORIGINAL BALANCE PRECISION
    # ---------------------------------------------------------

    op.alter_column(
        "accounts",
        "balance",
        existing_type=sa.Numeric(
            precision=30,
            scale=18,
        ),
        type_=sa.NUMERIC(
            precision=20,
            scale=8,
        ),
        existing_nullable=False,
    )

    # ---------------------------------------------------------
    # RENAME COLUMN BACK
    # ---------------------------------------------------------
    #
    # Preserve the synchronization data during downgrade too.
    #

    op.alter_column(
        "accounts",
        "last_synced_at",
        new_column_name="balance_updated_at",
    )

    # ---------------------------------------------------------
    # REMOVE PROVIDER FIELDS
    # ---------------------------------------------------------

    op.drop_column(
        "accounts",
        "external_account_id",
    )

    op.drop_column(
        "accounts",
        "provider",
    )