"""upgrade asset model

Revision ID: 339370183c57
Revises: 1324dff871db
Create Date: 2026-08-11 16:14:38.339406

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# =========================================================
# REVISION IDENTIFIERS
# =========================================================

revision: str = "339370183c57"

down_revision: Union[str, Sequence[str], None] = "1324dff871db"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# =========================================================
# UPGRADE
# =========================================================

def upgrade() -> None:
    """Upgrade the assets table to the production-ready model."""

    # -----------------------------------------------------
    # 1. ADD NEW COLUMNS
    # -----------------------------------------------------
    #
    # Important:
    # pricing_currency is temporarily nullable because
    # existing assets need to be backfilled from the old
    # quote_currency column before the NOT NULL constraint
    # can safely be applied.
    #

    op.add_column(
        "assets",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "is_market_backed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "valuation_method",
            sa.String(length=30),
            server_default=sa.text("'MANUAL'"),
            nullable=False,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "pricing_currency",
            sa.String(length=10),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "unit",
            sa.String(length=30),
            server_default=sa.text("'UNIT'"),
            nullable=False,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "market_data_provider",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "external_asset_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    # -----------------------------------------------------
    # 2. MIGRATE EXISTING ASSET DATA
    # -----------------------------------------------------
    #
    # Old:
    #     external_id
    #
    # New:
    #     external_asset_id
    #
    # Preserve the existing external identifier.
    #

    op.execute(
        """
        UPDATE assets
        SET external_asset_id = external_id
        WHERE external_id IS NOT NULL
        """
    )

    # -----------------------------------------------------
    # 3. MIGRATE QUOTE CURRENCY
    # -----------------------------------------------------
    #
    # Old:
    #     quote_currency
    #
    # New:
    #     pricing_currency
    #
    # Preserve the existing pricing currency.
    #

    op.execute(
        """
        UPDATE assets
        SET pricing_currency = quote_currency
        WHERE quote_currency IS NOT NULL
        """
    )

    # -----------------------------------------------------
    # 4. SAFELY HANDLE MISSING PRICING CURRENCIES
    # -----------------------------------------------------
    #
    # Existing assets without a quote currency need a valid
    # pricing currency before the column becomes NOT NULL.
    #
    # USD is used only as the migration fallback for legacy
    # records that did not have a quote currency recorded.
    #
    # Newly created assets should always provide an explicit
    # pricing_currency through the application/schema.
    #

    op.execute(
        """
        UPDATE assets
        SET pricing_currency = 'USD'
        WHERE pricing_currency IS NULL
        """
    )

    # -----------------------------------------------------
    # 5. IDENTIFY EXISTING MARKET-BACKED ASSETS
    # -----------------------------------------------------
    #
    # Legacy market assets have both:
    #
    #     market
    #     external_id
    #
    # populated.
    #
    # These should not silently become MANUAL assets.
    #
    # Example:
    #
    #     AAPL
    #     market = NASDAQ
    #     external_id = AAPL
    #     quote_currency = USD
    #
    # becomes:
    #
    #     is_market_backed = TRUE
    #     valuation_method = MARKET
    #     pricing_currency = USD
    #     external_asset_id = AAPL
    #
    # market_data_provider remains NULL because the legacy
    # `market` field represented an exchange/market, not
    # necessarily the actual market-data API provider.
    #

    op.execute(
        """
        UPDATE assets
        SET
            is_market_backed = true,
            valuation_method = 'MARKET'
        WHERE market IS NOT NULL
          AND external_id IS NOT NULL
        """
    )

    # -----------------------------------------------------
    # 6. SET APPROPRIATE UNITS FOR EXISTING STOCK ASSETS
    # -----------------------------------------------------
    #
    # Stocks represent shares rather than generic units.
    #

    op.execute(
        """
        UPDATE assets
        SET unit = 'SHARE'
        WHERE LOWER(asset_type) IN (
            'stock',
            'stocks',
            'share',
            'shares'
        )
        """
    )

    # -----------------------------------------------------
    # 7. ENFORCE PRICING CURRENCY
    # -----------------------------------------------------
    #
    # At this point every existing row has a value.
    #

    op.alter_column(
        "assets",
        "pricing_currency",
        existing_type=sa.String(length=10),
        nullable=False,
    )

    # -----------------------------------------------------
    # 8. REMOVE LEGACY INDEXES
    # -----------------------------------------------------

    op.drop_index(
        op.f("ix_assets_asset_type"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_external_id"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_is_active"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_market"),
        table_name="assets",
    )

    op.drop_index(
        op.f("ix_assets_symbol"),
        table_name="assets",
    )

    # -----------------------------------------------------
    # 9. CREATE NEW INDEXES
    # -----------------------------------------------------

    op.create_index(
        "ix_assets_provider_external_id",
        "assets",
        [
            "market_data_provider",
            "external_asset_id",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assets_type_active",
        "assets",
        [
            "asset_type",
            "is_active",
        ],
        unique=False,
    )

    # -----------------------------------------------------
    # 10. UNIQUE MARKET-DATA IDENTIFIER
    # -----------------------------------------------------
    #
    # A provider + external asset ID combination must identify
    # one asset.
    #
    # The partial condition allows manual/non-market assets
    # to have NULL provider/external IDs.
    #

    op.create_index(
        "uq_assets_provider_external_id",
        "assets",
        [
            "market_data_provider",
            "external_asset_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            """
            market_data_provider IS NOT NULL
            AND external_asset_id IS NOT NULL
            """
        ),
    )

    # -----------------------------------------------------
    # 11. UNIQUE ACTIVE SYMBOL
    # -----------------------------------------------------
    #
    # Asset records are treated as a shared asset catalog.
    #
    # Therefore an active symbol such as AAPL should represent
    # one asset definition rather than multiple duplicate
    # asset definitions.
    #
    # Case-insensitive uniqueness prevents:
    #
    #     AAPL
    #     aapl
    #     Aapl
    #
    # from becoming separate active assets.
    #

    op.create_index(
        "uq_assets_symbol_active",
        "assets",
        [
            sa.literal_column("lower(symbol)"),
        ],
        unique=True,
        postgresql_where=sa.text(
            """
            symbol IS NOT NULL
            AND is_active = true
            """
        ),
    )

    # -----------------------------------------------------
    # 12. VALIDATE VALUATION CONFIGURATION
    # -----------------------------------------------------
    #
    # Market-backed assets must use MARKET valuation.
    #
    # Non-market assets may use:
    #
    #     MANUAL
    #     MARKET_ASSISTED
    #
    # This prevents contradictory configurations.
    #

    op.create_check_constraint(
        "ck_assets_valuation_configuration",
        "assets",
        """
        (
            is_market_backed = true
            AND valuation_method = 'MARKET'
        )
        OR
        (
            is_market_backed = false
            AND valuation_method IN (
                'MANUAL',
                'MARKET_ASSISTED'
            )
        )
        """,
    )

    # -----------------------------------------------------
    # 13. REMOVE LEGACY COLUMNS
    # -----------------------------------------------------
    #
    # The data has already been migrated above.
    #

    op.drop_column(
        "assets",
        "quote_currency",
    )

    op.drop_column(
        "assets",
        "market",
    )

    op.drop_column(
        "assets",
        "external_id",
    )


# =========================================================
# DOWNGRADE
# =========================================================

def downgrade() -> None:
    """Restore the previous assets table structure."""

    # -----------------------------------------------------
    # 1. RESTORE LEGACY COLUMNS
    # -----------------------------------------------------

    op.add_column(
        "assets",
        sa.Column(
            "external_id",
            sa.VARCHAR(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "market",
            sa.VARCHAR(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "assets",
        sa.Column(
            "quote_currency",
            sa.VARCHAR(length=10),
            nullable=True,
        ),
    )

    # -----------------------------------------------------
    # 2. RESTORE LEGACY DATA
    # -----------------------------------------------------

    op.execute(
        """
        UPDATE assets
        SET
            external_id = external_asset_id,
            quote_currency = pricing_currency
        WHERE external_asset_id IS NOT NULL
        """
    )

    # -----------------------------------------------------
    # 3. REMOVE NEW CONSTRAINTS / INDEXES
    # -----------------------------------------------------

    op.drop_constraint(
        "ck_assets_valuation_configuration",
        "assets",
        type_="check",
    )

    op.drop_index(
        "uq_assets_symbol_active",
        table_name="assets",
        postgresql_where=sa.text(
            """
            symbol IS NOT NULL
            AND is_active = true
            """
        ),
    )

    op.drop_index(
        "uq_assets_provider_external_id",
        table_name="assets",
        postgresql_where=sa.text(
            """
            market_data_provider IS NOT NULL
            AND external_asset_id IS NOT NULL
            """
        ),
    )

    op.drop_index(
        "ix_assets_type_active",
        table_name="assets",
    )

    op.drop_index(
        "ix_assets_provider_external_id",
        table_name="assets",
    )

    # -----------------------------------------------------
    # 4. RESTORE LEGACY INDEXES
    # -----------------------------------------------------

    op.create_index(
        op.f("ix_assets_symbol"),
        "assets",
        ["symbol"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_market"),
        "assets",
        ["market"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_is_active"),
        "assets",
        ["is_active"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_external_id"),
        "assets",
        ["external_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_assets_asset_type"),
        "assets",
        ["asset_type"],
        unique=False,
    )

    # -----------------------------------------------------
    # 5. REMOVE NEW COLUMNS
    # -----------------------------------------------------

    op.drop_column(
        "assets",
        "external_asset_id",
    )

    op.drop_column(
        "assets",
        "market_data_provider",
    )

    op.drop_column(
        "assets",
        "unit",
    )

    op.drop_column(
        "assets",
        "pricing_currency",
    )

    op.drop_column(
        "assets",
        "valuation_method",
    )

    op.drop_column(
        "assets",
        "is_market_backed",
    )

    op.drop_column(
        "assets",
        "description",
    )