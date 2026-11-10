from backend.app.database.connection import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class Asset(Base):
    """
    Represents a canonical asset that Finova can track.

    An Asset describes WHAT the financial/investable thing is.

    A Holding describes HOW MUCH of that asset a particular
    user owns.

    Transactions describe HOW the asset was acquired, disposed
    of, transferred, or otherwise transacted.

    Asset does NOT store:
        - user ownership
        - quantity owned
        - purchase price
        - cost basis
        - current market price
        - current market value
        - unrealized profit/loss

    Those responsibilities belong to Holdings, Transactions,
    and the valuation/market-data layer respectively.

    Assets may be:

    Market-backed:
        - Stocks
        - ETFs
        - Shares
        - Crypto
        - Forex
        - Commodities
        - Other exchange-traded instruments

    Non-market / manually valued:
        - Physical gold
        - Gold watches
        - Diamonds
        - Collectibles
        - Real estate
        - Businesses
        - Physical cash
        - Other tangible or manually valued assets

    Market-backed assets can obtain their current valuation
    through Finova's market-data infrastructure.

    Non-market assets use manual valuation.

    Asset identity is deliberately separated from valuation.
    """

    __tablename__ = "assets"

    # =========================================================
    # TABLE CONSTRAINTS / INDEXES
    # =========================================================

    __table_args__ = (

        # -----------------------------------------------------
        # Efficient filtering by asset type and active status.
        # -----------------------------------------------------
        Index(
            "ix_assets_type_active",
            "asset_type",
            "is_active",
        ),

        # -----------------------------------------------------
        # Efficient lookup of provider mappings.
        # -----------------------------------------------------
        Index(
            "ix_assets_provider_external_id",
            "market_data_provider",
            "external_asset_id",
        ),

        # -----------------------------------------------------
        # A provider's external asset ID uniquely identifies
        # an asset within that provider.
        #
        # NULL values are intentionally allowed because
        # manually-created assets do not require a provider
        # mapping.
        # -----------------------------------------------------
        Index(
            "uq_assets_provider_external_id",
            "market_data_provider",
            "external_asset_id",
            unique=True,
            postgresql_where=text(
                "market_data_provider IS NOT NULL "
                "AND external_asset_id IS NOT NULL"
            ),
        ),

        # -----------------------------------------------------
        # Market-backed / exchange-identified assets.
        #
        # The same symbol may exist on different markets.
        #
        # Examples:
        #
        #     AAPL + NASDAQ
        #     AAPL + NYSE
        #
        # are treated as distinct asset identities.
        #
        # Comparison is case-insensitive.
        #
        # Only active assets participate in the constraint.
        # -----------------------------------------------------
        Index(
            "uq_assets_symbol_market_active",
            text("lower(symbol)"),
            text("lower(market)"),
            unique=True,
            postgresql_where=text(
                "symbol IS NOT NULL "
                "AND market IS NOT NULL "
                "AND is_active = true"
            ),
        ),

        # -----------------------------------------------------
        # Assets with a symbol but no explicit market.
        #
        # Example:
        #
        #     BTC
        #
        # This prevents duplicate canonical assets such as:
        #
        #     BTC
        #     btc
        #
        # when no market has been specified.
        # -----------------------------------------------------
        Index(
            "uq_assets_symbol_no_market_active",
            text("lower(symbol)"),
            unique=True,
            postgresql_where=text(
                "symbol IS NOT NULL "
                "AND market IS NULL "
                "AND is_active = true"
            ),
        ),

        # -----------------------------------------------------
        # Valuation configuration must remain internally
        # consistent.
        #
        # MARKET assets:
        #     is_market_backed = true
        #     valuation_method = MARKET
        #
        # MANUAL assets:
        #     is_market_backed = false
        #     valuation_method = MANUAL
        # -----------------------------------------------------
        CheckConstraint(
            """
            (
                is_market_backed = true
                AND valuation_method = 'MARKET'
            )
            OR
            (
                is_market_backed = false
                AND valuation_method = 'MANUAL'
            )
            """,
            name="ck_assets_valuation_configuration",
        ),

        # -----------------------------------------------------
        # Market-data provider and external ID must be supplied
        # together.
        #
        # Either both are present or both are NULL.
        # -----------------------------------------------------
        CheckConstraint(
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
            name="ck_assets_provider_external_id_pair",
        ),
    )

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # ASSET IDENTITY
    # =========================================================

    # Human-readable canonical asset name.
    #
    # Examples:
    #     Apple Inc.
    #     Bitcoin
    #     Rolex Gold Watch
    #     Physical Gold
    #     Lekki Property
    name = Column(
        String(150),
        nullable=False,
    )

    # ---------------------------------------------------------
    # SYMBOL
    # ---------------------------------------------------------

    # Canonical/user-defined identifier for the asset.
    #
    # Market examples:
    #     AAPL
    #     MSFT
    #     BTC
    #     EUR/USD
    #
    # Non-market examples:
    #     GOLD-WATCH-001
    #     DIAMOND-001
    #     CASH-NGN
    #
    # Nullable because manually tracked assets do not
    # necessarily need a symbol.
    symbol = Column(
        String(50),
        nullable=True,
    )

    # ---------------------------------------------------------
    # ASSET TYPE
    # ---------------------------------------------------------

    # Examples:
    #
    # STOCK
    # ETF
    # CRYPTO
    # FOREX
    # COMMODITY
    # REAL_ESTATE
    # BUSINESS
    # PRECIOUS_METAL
    # COLLECTIBLE
    # CASH
    # OTHER
    asset_type = Column(
        String(30),
        nullable=False,
    )

    # ---------------------------------------------------------
    # DESCRIPTION
    # ---------------------------------------------------------

    # Additional information about the asset.
    description = Column(
        Text,
        nullable=True,
    )

    # =========================================================
    # MARKET / EXCHANGE INFORMATION
    # =========================================================

    # Exchange or market where the asset is traded.
    #
    # Examples:
    #     NASDAQ
    #     NYSE
    #     LSE
    #     Binance
    #
    # This is deliberately separate from the market-data
    # provider.
    #
    # Example:
    #     market = NASDAQ
    #     market_data_provider = polygon
    market = Column(
        String(100),
        nullable=True,
    )

    # =========================================================
    # VALUATION CONFIGURATION
    # =========================================================

    # Whether current valuation can be obtained from external
    # market-data infrastructure.
    #
    # True:
    #     AAPL
    #     BTC
    #     MSFT
    #
    # False:
    #     Physical gold
    #     Gold watch
    #     Diamond
    #     Real estate
    #     Physical cash
    is_market_backed = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    # How Finova obtains the current valuation.
    #
    # MARKET:
    #     Current price comes from market-data infrastructure.
    #
    # MANUAL:
    #     Current valuation is supplied manually.
    valuation_method = Column(
        String(30),
        nullable=False,
        default="MANUAL",
        server_default=text("'MANUAL'"),
    )

    # Currency in which the asset's price/value is expressed.
    #
    # Examples:
    #     USD
    #     NGN
    #     EUR
    #
    # Example:
    #     BTC may have pricing_currency = USD.
    pricing_currency = Column(
        String(10),
        nullable=False,
    )

    # What one unit of the asset represents.
    #
    # Examples:
    #     SHARE
    #     COIN
    #     UNIT
    #     OUNCE
    #     GRAM
    #     CURRENCY
    #     SQ_METER
    unit = Column(
        String(30),
        nullable=False,
        default="UNIT",
        server_default=text("'UNIT'"),
    )

    # =========================================================
    # MARKET DATA INTEGRATION
    # =========================================================

    # External market-data provider.
    #
    # Examples:
    #     polygon
    #     alphavantage
    #     coingecko
    #
    # This is NOT the exchange/market.
    market_data_provider = Column(
        String(50),
        nullable=True,
    )

    # Identifier assigned by the external market-data provider.
    #
    # This may differ from the public symbol.
    external_asset_id = Column(
        String(255),
        nullable=True,
    )

    # =========================================================
    # STATUS / LIFECYCLE
    # =========================================================

    # Assets are normally deactivated rather than physically
    # deleted because historical holdings and transactions may
    # reference them.
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # Holdings that reference this asset.
    #
    # No delete cascade is configured because historical
    # holdings must not disappear automatically.
    holdings = relationship(
        "Holding",
        back_populates="asset",
    )

    # Transactions involving this asset.
    #
    # No delete cascade is configured because transactions
    # represent financial history.
    transactions = relationship(
        "Transaction",
        back_populates="asset",
    )

    # Scheduled transactions involving this asset.
    #
    # This is the inverse side of ScheduledTransaction.asset.
    # No delete cascade is configured because scheduled
    # transaction definitions should not disappear merely
    # because an asset is deactivated.
    scheduled_transactions = relationship(
        "ScheduledTransaction",
        back_populates="asset",
    )