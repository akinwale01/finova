"""Synchronize account portfolio and user schema

Revision ID: c48838dfa275
Revises: 9b96559547a3
Create Date: 2026-08-15 17:44:28.264106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c48838dfa275"
down_revision: Union[str, Sequence[str], None] = "9b96559547a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Synchronize account, portfolio, and user schema."""

    # =========================================================
    # ACCOUNTS
    # =========================================================

    # A connected external account must have a unique
    # provider/external-account combination.
    op.create_index(
        "uq_accounts_provider_external_id_connected",
        "accounts",
        ["provider", "external_account_id"],
        unique=True,
        postgresql_where=sa.text("is_connected = true"),
    )

    # Prevent accidental deletion of a user that still owns
    # financial accounts.
    op.drop_constraint(
        "accounts_user_id_fkey",
        "accounts",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "accounts_user_id_fkey",
        "accounts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # The previous balance >= 0 constraint is removed because
    # account balances may legitimately become negative
    # depending on the account type and financial activity.
    op.drop_constraint(
        "ck_accounts_balance_non_negative",
        "accounts",
        type_="check",
    )

    # Currency codes are stored as uppercase alphanumeric
    # identifiers between 3 and 10 characters.
    op.create_check_constraint(
        "ck_accounts_currency_format",
        "accounts",
        "currency ~ '^[A-Z0-9]{3,10}$'",
    )

    # =========================================================
    # PORTFOLIOS
    # =========================================================

    # Prevent accidental deletion of a user that still owns
    # portfolios.
    op.drop_constraint(
        "portfolios_user_id_fkey",
        "portfolios",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "portfolios_user_id_fkey",
        "portfolios",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # =========================================================
    # USERS
    # =========================================================

    # Password-reset credentials are stored as a hash rather
    # than as a plaintext reset token.
    op.add_column(
        "users",
        sa.Column(
            "password_reset_token_hash",
            sa.String(length=255),
            nullable=True,
        ),
    )

    # Expiration timestamp for the password-reset token.
    op.add_column(
        "users",
        sa.Column(
            "password_reset_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revert account, portfolio, and user schema synchronization."""

    # =========================================================
    # USERS
    # =========================================================

    op.drop_column(
        "users",
        "password_reset_expires_at",
    )

    op.drop_column(
        "users",
        "password_reset_token_hash",
    )

    # =========================================================
    # PORTFOLIOS
    # =========================================================

    op.drop_constraint(
        "portfolios_user_id_fkey",
        "portfolios",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "portfolios_user_id_fkey",
        "portfolios",
        "users",
        ["user_id"],
        ["id"],
    )

    # =========================================================
    # ACCOUNTS
    # =========================================================

    op.drop_constraint(
        "ck_accounts_currency_format",
        "accounts",
        type_="check",
    )

    op.create_check_constraint(
        "ck_accounts_balance_non_negative",
        "accounts",
        "balance >= 0::numeric",
    )

    op.drop_constraint(
        "accounts_user_id_fkey",
        "accounts",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "accounts_user_id_fkey",
        "accounts",
        "users",
        ["user_id"],
        ["id"],
    )

    op.drop_index(
        "uq_accounts_provider_external_id_connected",
        table_name="accounts",
        postgresql_where=sa.text("is_connected = true"),
    )