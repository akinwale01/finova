"""Finalize holdings model.

Revision ID: 2f5f69995abd
Revises: eaddc0ff4718
Create Date: 2026-08-25 12:40:10.783052

This migration finalizes the production Holding schema.

Key changes:
- Separates historical cost basis from current valuation.
- Adds cost basis currency and valuation currency.
- Enforces one holding per portfolio/asset pair.
- Adds non-negative/range validation constraints.
- Changes Holding foreign keys to explicit RESTRICT behavior.
- Removes the legacy currency column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision: str = "2f5f69995abd"
down_revision: Union[str, Sequence[str], None] = "eaddc0ff4718"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade() -> None:
    """Finalize the production Holding schema."""

    # --------------------------------------------------------
    # COST BASIS
    # --------------------------------------------------------
    #
    # Historical acquisition information must remain separate
    # from live market valuation.
    #
    # total_cost_basis:
    #     Total historical amount invested in the holding.
    #
    # cost_basis_per_unit:
    #     Average historical acquisition cost per unit.
    #
    # These values must NOT be overwritten when market prices
    # change.
    #

    op.add_column(
        "holdings",
        sa.Column(
            "total_cost_basis",
            sa.Numeric(precision=20, scale=8),
            server_default="0",
            nullable=False,
        ),
    )

    op.add_column(
        "holdings",
        sa.Column(
            "cost_basis_per_unit",
            sa.Numeric(precision=20, scale=8),
            server_default="0",
            nullable=False,
        ),
    )

    # --------------------------------------------------------
    # COST BASIS CURRENCY
    # --------------------------------------------------------
    #
    # The old `currency` column represented the holding's
    # valuation currency.
    #
    # Cost basis needs its own currency because acquisition
    # history and current valuation may use different currencies.
    #
    # Example:
    #
    #   Cost basis: USD
    #   Current valuation: NGN
    #
    # Add this as nullable first so the migration remains safe
    # if historical rows already exist.
    #

    op.add_column(
        "holdings",
        sa.Column(
            "cost_basis_currency",
            sa.String(length=3),
            nullable=True,
        ),
    )

    # --------------------------------------------------------
    # VALUATION CURRENCY
    # --------------------------------------------------------
    #
    # Current valuation may be represented in a currency that
    # differs from the original acquisition currency.
    #

    op.add_column(
        "holdings",
        sa.Column(
            "valuation_currency",
            sa.String(length=3),
            nullable=True,
        ),
    )

    # --------------------------------------------------------
    # MIGRATE EXISTING CURRENCY DATA
    # --------------------------------------------------------
    #
    # Existing databases may contain rows using the old
    # `currency` column.
    #
    # Preserve that information before removing the column.
    #
    # The current database contains zero holdings, but this makes
    # the migration safer for databases containing historical data.
    #

    op.execute(
        """
        UPDATE holdings
        SET
            cost_basis_currency = currency,
            valuation_currency = currency
        WHERE currency IS NOT NULL
        """
    )

    # cost_basis_currency is required by the finalized model.
    op.alter_column(
        "holdings",
        "cost_basis_currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )

    # --------------------------------------------------------
    # UNIQUE HOLDING PER PORTFOLIO / ASSET
    # --------------------------------------------------------
    #
    # A portfolio should have exactly one canonical Holding row
    # for a particular Asset.
    #
    # Example:
    #
    #   Portfolio A + Apple = one Holding
    #
    # Additional purchases are represented through Transactions
    # and update the existing Holding rather than creating
    # duplicate Holding rows.
    #

    op.create_index(
        "uq_holdings_portfolio_asset",
        "holdings",
        ["portfolio_id", "asset_id"],
        unique=True,
    )

    # --------------------------------------------------------
    # FOREIGN KEYS
    # --------------------------------------------------------
    #
    # Replace the previous unnamed/default foreign keys with
    # explicitly named production constraints.
    #
    # RESTRICT prevents deletion of a Portfolio or Asset while
    # historical/current holdings still reference it.
    #

    op.drop_constraint(
        op.f("holdings_asset_id_fkey"),
        "holdings",
        type_="foreignkey",
    )

    op.drop_constraint(
        op.f("holdings_portfolio_id_fkey"),
        "holdings",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_holdings_portfolio_id",
        "holdings",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_holdings_asset_id",
        "holdings",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # --------------------------------------------------------
    # CHECK CONSTRAINTS
    # --------------------------------------------------------

    # Cost basis per unit cannot be negative.
    op.create_check_constraint(
        "ck_holdings_cost_basis_per_unit_non_negative",
        "holdings",
        "cost_basis_per_unit >= 0",
    )

    # Current total valuation cannot be negative.
    #
    # NULL is allowed because a current market valuation may not
    # yet exist.
    op.create_check_constraint(
        "ck_holdings_current_total_value_non_negative",
        "holdings",
        """
        current_total_value IS NULL
        OR current_total_value >= 0
        """,
    )

    # Current unit price cannot be negative.
    #
    # NULL is allowed when no current price is available.
    op.create_check_constraint(
        "ck_holdings_current_unit_price_non_negative",
        "holdings",
        """
        current_unit_price IS NULL
        OR current_unit_price >= 0
        """,
    )

    # Ownership percentage must be between 0 and 100.
    #
    # NULL is allowed because most assets are not
    # ownership-percentage-based.
    op.create_check_constraint(
        "ck_holdings_ownership_percentage_range",
        "holdings",
        """
        ownership_percentage IS NULL
        OR (
            ownership_percentage >= 0
            AND ownership_percentage <= 100
        )
        """,
    )

    # Quantity cannot be negative.
    op.create_check_constraint(
        "ck_holdings_quantity_non_negative",
        "holdings",
        "quantity >= 0",
    )

    # Total historical cost basis cannot be negative.
    op.create_check_constraint(
        "ck_holdings_total_cost_basis_non_negative",
        "holdings",
        "total_cost_basis >= 0",
    )

    # --------------------------------------------------------
    # REMOVE LEGACY CURRENCY COLUMN
    # --------------------------------------------------------
    #
    # Currency is now explicitly represented by:
    #
    #   cost_basis_currency
    #   valuation_currency
    #
    # Keeping the old generic currency field would create
    # ambiguity about which currency a value represents.
    #

    op.drop_column(
        "holdings",
        "currency",
    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade() -> None:
    """Restore the previous Holding schema."""

    # --------------------------------------------------------
    # RESTORE LEGACY CURRENCY COLUMN
    # --------------------------------------------------------
    #
    # Add it as nullable first so existing rows can be safely
    # populated before enforcing NOT NULL.
    #

    op.add_column(
        "holdings",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=True,
        ),
    )

    # Restore the best available valuation currency.
    #
    # Prefer valuation_currency because the legacy `currency`
    # represented the holding's valuation currency.
    #
    # Fall back to cost_basis_currency if valuation_currency
    # was unavailable.
    op.execute(
        """
        UPDATE holdings
        SET currency = COALESCE(
            valuation_currency,
            cost_basis_currency
        )
        """
    )

    # The old schema required currency.
    op.alter_column(
        "holdings",
        "currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )

    # --------------------------------------------------------
    # REMOVE CHECK CONSTRAINTS
    # --------------------------------------------------------

    op.drop_constraint(
        "ck_holdings_total_cost_basis_non_negative",
        "holdings",
        type_="check",
    )

    op.drop_constraint(
        "ck_holdings_quantity_non_negative",
        "holdings",
        type_="check",
    )

    op.drop_constraint(
        "ck_holdings_ownership_percentage_range",
        "holdings",
        type_="check",
    )

    op.drop_constraint(
        "ck_holdings_current_unit_price_non_negative",
        "holdings",
        type_="check",
    )

    op.drop_constraint(
        "ck_holdings_current_total_value_non_negative",
        "holdings",
        type_="check",
    )

    op.drop_constraint(
        "ck_holdings_cost_basis_per_unit_non_negative",
        "holdings",
        type_="check",
    )

    # --------------------------------------------------------
    # REMOVE EXPLICIT FOREIGN KEYS
    # --------------------------------------------------------

    op.drop_constraint(
        "fk_holdings_asset_id",
        "holdings",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_holdings_portfolio_id",
        "holdings",
        type_="foreignkey",
    )

    # Restore the original foreign keys.
    op.create_foreign_key(
        op.f("holdings_portfolio_id_fkey"),
        "holdings",
        "portfolios",
        ["portfolio_id"],
        ["id"],
    )

    op.create_foreign_key(
        op.f("holdings_asset_id_fkey"),
        "holdings",
        "assets",
        ["asset_id"],
        ["id"],
    )

    # --------------------------------------------------------
    # REMOVE UNIQUE HOLDING CONSTRAINT
    # --------------------------------------------------------

    op.drop_index(
        "uq_holdings_portfolio_asset",
        table_name="holdings",
    )

    # --------------------------------------------------------
    # REMOVE NEW CURRENCY FIELDS
    # --------------------------------------------------------

    op.drop_column(
        "holdings",
        "valuation_currency",
    )

    op.drop_column(
        "holdings",
        "cost_basis_currency",
    )

    # --------------------------------------------------------
    # REMOVE COST BASIS FIELDS
    # --------------------------------------------------------

    op.drop_column(
        "holdings",
        "cost_basis_per_unit",
    )

    op.drop_column(
        "holdings",
        "total_cost_basis",
    )