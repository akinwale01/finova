"""Finalize transaction model

Revision ID: 28e87c474a91
Revises: c48838dfa275
Create Date: 2026-08-15 18:29:39.449578

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "28e87c474a91"
down_revision: str | Sequence[str] | None = "c48838dfa275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the final Transaction schema constraints and indexes."""

    # =========================================================
    # TRANSACTION HISTORY INDEXES
    # =========================================================

    # Portfolio transaction history ordered chronologically.
    op.create_index(
        "ix_transactions_portfolio_date",
        "transactions",
        ["portfolio_id", "transaction_date"],
        unique=False,
    )

    # Source-account transaction history ordered chronologically.
    op.create_index(
        "ix_transactions_source_account_date",
        "transactions",
        ["source_account_id", "transaction_date"],
        unique=False,
    )

    # Destination-account transaction history ordered
    # chronologically.
    op.create_index(
        "ix_transactions_destination_account_date",
        "transactions",
        ["destination_account_id", "transaction_date"],
        unique=False,
    )

    # Efficient filtering by transaction type and execution status.
    op.create_index(
        "ix_transactions_type_status",
        "transactions",
        ["transaction_type", "status"],
        unique=False,
    )

    # =========================================================
    # EXTERNAL REFERENCE
    # =========================================================

    # IMPORTANT:
    #
    # external_reference is intentionally NOT unique.
    #
    # Finova has not yet established the correct uniqueness
    # boundary for externally supplied transaction references.
    #
    # The Transaction model provides a normal lookup index:
    #
    #     ix_transactions_external_reference
    #
    # No unique constraint is created here.
    #
    # The correct uniqueness rule will be established only after
    # the external-provider/import architecture is defined.

    # =========================================================
    # FOREIGN KEYS
    # =========================================================

    # Replace the original foreign keys so referenced financial
    # records cannot be deleted while transactions still refer
    # to them.

    op.drop_constraint(
        "transactions_portfolio_id_fkey",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "transactions_asset_id_fkey",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "transactions_destination_account_id_fkey",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "transactions_source_account_id_fkey",
        "transactions",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_transactions_asset_id_assets",
        "transactions",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_transactions_portfolio_id_portfolios",
        "transactions",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_transactions_source_account_id_accounts",
        "transactions",
        "accounts",
        ["source_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_transactions_destination_account_id_accounts",
        "transactions",
        "accounts",
        ["destination_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Revert the final Transaction schema constraints and indexes."""

    # =========================================================
    # FOREIGN KEYS
    # =========================================================

    op.drop_constraint(
        "fk_transactions_destination_account_id_accounts",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_transactions_source_account_id_accounts",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_transactions_portfolio_id_portfolios",
        "transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_transactions_asset_id_assets",
        "transactions",
        type_="foreignkey",
    )

    # Restore the original foreign-key definitions.
    op.create_foreign_key(
        "transactions_source_account_id_fkey",
        "transactions",
        "accounts",
        ["source_account_id"],
        ["id"],
    )

    op.create_foreign_key(
        "transactions_destination_account_id_fkey",
        "transactions",
        "accounts",
        ["destination_account_id"],
        ["id"],
    )

    op.create_foreign_key(
        "transactions_asset_id_fkey",
        "transactions",
        "assets",
        ["asset_id"],
        ["id"],
    )

    op.create_foreign_key(
        "transactions_portfolio_id_fkey",
        "transactions",
        "portfolios",
        ["portfolio_id"],
        ["id"],
    )

    # =========================================================
    # INDEXES
    # =========================================================

    op.drop_index(
        "ix_transactions_type_status",
        table_name="transactions",
    )

    op.drop_index(
        "ix_transactions_destination_account_date",
        table_name="transactions",
    )

    op.drop_index(
        "ix_transactions_source_account_date",
        table_name="transactions",
    )

    op.drop_index(
        "ix_transactions_portfolio_date",
        table_name="transactions",
    )