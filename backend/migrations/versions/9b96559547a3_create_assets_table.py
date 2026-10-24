"""Refine asset identity and provider mapping constraints.

Revision ID: 9b96559547a3
Revises: 69bf01b49463
Create Date: 2026-08-15 17:11:22.512709

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "9b96559547a3"
down_revision: Union[str, Sequence[str], None] = "69bf01b49463"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Apply the Asset identity and market-data provider
    integrity changes.

    This migration intentionally contains ONLY Asset changes.

    Existing orphaned external_asset_id values are cleared
    before the new provider/external-ID pairing constraint is
    added. We do not invent provider names for historical data.
    """

    # =========================================================
    # 1. REMOVE THE OLD SYMBOL UNIQUENESS RULE
    # =========================================================

    # The previous rule treated every active symbol as globally
    # unique, regardless of market.
    #
    # That is too restrictive because the same symbol can exist
    # on different markets.
    op.drop_index(
        "uq_assets_symbol_active",
        table_name="assets",
    )

    # =========================================================
    # 2. ADD MARKET-AWARE SYMBOL UNIQUENESS
    # =========================================================

    # Same symbol + same market cannot represent two active
    # canonical assets.
    #
    # Comparison is case-insensitive.
    op.create_index(
        "uq_assets_symbol_market_active",
        "assets",
        [
            sa.literal_column("lower(symbol)"),
            sa.literal_column("lower(market)"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "symbol IS NOT NULL "
            "AND market IS NOT NULL "
            "AND is_active = true"
        ),
    )

    # =========================================================
    # 3. ADD SYMBOL UNIQUENESS WHEN NO MARKET EXISTS
    # =========================================================

    # If an asset has a symbol but no explicit market, that
    # symbol must still uniquely identify the active asset.
    op.create_index(
        "uq_assets_symbol_no_market_active",
        "assets",
        [
            sa.literal_column("lower(symbol)"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "symbol IS NOT NULL "
            "AND market IS NULL "
            "AND is_active = true"
        ),
    )

    # =========================================================
    # 4. NORMALIZE EXISTING PROVIDER MAPPINGS
    # =========================================================

    # Historical Asset rows may contain an external_asset_id
    # without a corresponding market_data_provider.
    #
    # An external ID has meaning only within a provider namespace.
    #
    # We therefore remove orphaned external IDs instead of
    # inventing a provider that we cannot reliably determine.
    op.execute(
        sa.text(
            """
            UPDATE assets
            SET
                external_asset_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                market_data_provider IS NULL
                AND external_asset_id IS NOT NULL
            """
        )
    )

    # =========================================================
    # 5. ENFORCE PROVIDER / EXTERNAL-ID PAIRING
    # =========================================================

    # Both values must either be present together or be NULL.
    #
    # This prevents invalid states such as:
    #
    #     provider = NULL
    #     external_asset_id = "AAPL"
    #
    # or:
    #
    #     provider = "polygon"
    #     external_asset_id = NULL
    op.create_check_constraint(
        "ck_assets_provider_external_id_pair",
        "assets",
        """
        (
            market_data_provider IS NULL
            AND external_asset_id IS NULL
        )
        OR
        (
            market_data_provider IS NOT NULL
            AND external_asset_id IS NOT NULL
        )
        """,
    )


def downgrade() -> None:
    """
    Reverse the Asset identity and provider mapping changes.

    Note:
    External IDs that were intentionally cleared during the
    upgrade cannot be reconstructed during downgrade because
    their original provider mapping was unknown.
    """

    # =========================================================
    # 1. REMOVE PROVIDER / EXTERNAL-ID CONSTRAINT
    # =========================================================

    op.drop_constraint(
        "ck_assets_provider_external_id_pair",
        "assets",
        type_="check",
    )

    # =========================================================
    # 2. REMOVE MARKET-AWARE SYMBOL INDEXES
    # =========================================================

    op.drop_index(
        "uq_assets_symbol_no_market_active",
        table_name="assets",
    )

    op.drop_index(
        "uq_assets_symbol_market_active",
        table_name="assets",
    )

    # =========================================================
    # 3. RESTORE THE PREVIOUS SYMBOL UNIQUENESS RULE
    # =========================================================

    op.create_index(
        "uq_assets_symbol_active",
        "assets",
        [
            sa.literal_column("lower(symbol)"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "symbol IS NOT NULL "
            "AND is_active = true"
        ),
    )