from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.database.connection import Base


# ============================================================
# ENUMS
# ============================================================


class HoldingValuationMethod(str, Enum):
    """
    Defines how Finova determines the current value of a holding.

    MARKET_PRICE:
        Current value is based on a live/current market price
        obtained from the market-data layer.

    USER_VALUED:
        Current value is manually supplied by the user.

    CALCULATED:
        Current value is derived from another deterministic
        valuation method.
    """

    MARKET_PRICE = "MARKET_PRICE"
    USER_VALUED = "USER_VALUED"
    CALCULATED = "CALCULATED"


# ============================================================
# MODEL
# ============================================================


class Holding(Base):
    """
    Represents the current ownership position of an asset
    inside a portfolio.

    A Holding answers:

        "How much of this asset does this portfolio currently own?"

    The Asset model describes WHAT the asset is.

    The Holding model describes:
        - how much is currently owned
        - historical acquisition/cost-basis information
        - current valuation information

    IMPORTANT ARCHITECTURAL RULE:

        Historical acquisition data
            MUST NOT be overwritten by market-price changes.

        Current valuation
            MAY change whenever market data changes.

    Therefore:

        Cost basis
            = historical acquisition information

        Current value
            = current quantity × current valuation price
              with currency conversion when required

        Unrealized P/L
            = current value - cost basis

    Transactions remain the historical source of individual
    financial events.

    Holding is the current aggregate position derived from
    those events.
    """

    __tablename__ = "holdings"

    # =========================================================
    # DATABASE CONSTRAINTS / INDEXES
    # =========================================================

    __table_args__ = (

        # -----------------------------------------------------
        # A portfolio should have one canonical Holding for
        # each Asset.
        #
        # Example:
        #
        # Portfolio A + AAPL
        #     -> one Holding
        #
        # Additional purchases increase quantity/cost basis
        # rather than creating another Holding row.
        # -----------------------------------------------------
        Index(
            "uq_holdings_portfolio_asset",
            "portfolio_id",
            "asset_id",
            unique=True,
        ),

        # -----------------------------------------------------
        # Fast lookup of holdings belonging to a portfolio.
        # -----------------------------------------------------
        Index(
            "ix_holdings_portfolio_id",
            "portfolio_id",
        ),

        # -----------------------------------------------------
        # Fast lookup of portfolios holding an asset.
        # -----------------------------------------------------
        Index(
            "ix_holdings_asset_id",
            "asset_id",
        ),

        # -----------------------------------------------------
        # Quantity cannot be negative.
        #
        # A SELL that completely disposes of a position should
        # reduce quantity to zero rather than create a negative
        # Holding.
        # -----------------------------------------------------
        CheckConstraint(
            "quantity >= 0",
            name="ck_holdings_quantity_non_negative",
        ),

        # -----------------------------------------------------
        # Historical total cost basis cannot be negative.
        # -----------------------------------------------------
        CheckConstraint(
            "total_cost_basis >= 0",
            name="ck_holdings_total_cost_basis_non_negative",
        ),

        # -----------------------------------------------------
        # Average acquisition cost cannot be negative.
        # -----------------------------------------------------
        CheckConstraint(
            "cost_basis_per_unit >= 0",
            name="ck_holdings_cost_basis_per_unit_non_negative",
        ),

        # -----------------------------------------------------
        # Current valuation cannot be negative.
        # -----------------------------------------------------
        CheckConstraint(
            "current_unit_price IS NULL OR current_unit_price >= 0",
            name="ck_holdings_current_unit_price_non_negative",
        ),

        CheckConstraint(
            "current_total_value IS NULL OR current_total_value >= 0",
            name="ck_holdings_current_total_value_non_negative",
        ),

        # -----------------------------------------------------
        # Ownership percentage, when applicable, must be
        # between 0 and 100.
        # -----------------------------------------------------
        CheckConstraint(
            """
            ownership_percentage IS NULL
            OR (
                ownership_percentage >= 0
                AND ownership_percentage <= 100
            )
            """,
            name="ck_holdings_ownership_percentage_range",
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
    # PORTFOLIO
    # =========================================================

    # Portfolio currently containing this holding.
    portfolio_id = Column(
        Integer,
        ForeignKey(
            "portfolios.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # =========================================================
    # ASSET
    # =========================================================

    # Canonical asset represented by this holding.
    asset_id = Column(
        Integer,
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # =========================================================
    # CURRENT OWNERSHIP
    # =========================================================

    # Current quantity owned by the portfolio.
    #
    # Examples:
    #
    #     AAPL -> 25.00000000 shares
    #     BTC  -> 0.50000000 BTC
    #     Gold -> 500.00000000 grams
    #
    # This value represents the CURRENT position, not the
    # original acquisition quantity.
    quantity = Column(
        Numeric(20, 8),
        nullable=False,
    )

    # Unit corresponding to quantity.
    #
    # Examples:
    #
    #     SHARE
    #     BTC
    #     ETH
    #     GRAM
    #     UNIT
    unit = Column(
        String(30),
        nullable=False,
    )

    # =========================================================
    # OWNERSHIP-BASED ASSETS
    # =========================================================

    # Percentage ownership for assets such as:
    #
    #     private businesses
    #     partnerships
    #     private companies
    #
    # Example:
    #
    #     quantity = 1
    #     ownership_percentage = 25
    #
    # means the user owns 25% of the represented business.
    ownership_percentage = Column(
        Numeric(7, 4),
        nullable=True,
    )

    # =========================================================
    # HISTORICAL COST BASIS
    # =========================================================

    # Total historical acquisition cost currently represented
    # by the holding.
    #
    # IMPORTANT:
    #
    # This is NOT the current market value.
    #
    # It must NOT change merely because the market price changes.
    #
    # Example:
    #
    #     Bought 10 AAPL for $1,800
    #
    #     total_cost_basis = $1,800
    #
    # If AAPL later becomes $2,100:
    #
    #     total_cost_basis remains $1,800
    #     current_total_value becomes $2,100
    total_cost_basis = Column(
        Numeric(20, 8),
        nullable=False,
        default=0,
        server_default="0",
    )

    # Historical average acquisition cost per currently held
    # unit.
    #
    # This is derived from historical transaction activity and
    # cost-basis rules.
    #
    # It is NOT the current market price.
    cost_basis_per_unit = Column(
        Numeric(20, 8),
        nullable=False,
        default=0,
        server_default="0",
    )

    # Currency in which the historical cost basis is recorded.
    #
    # Examples:
    #
    #     USD
    #     NGN
    #     EUR
    cost_basis_currency = Column(
        String(3),
        nullable=False,
    )

    # =========================================================
    # CURRENT VALUATION
    # =========================================================

    # Defines how Finova obtains the current valuation.
    valuation_method = Column(
        String(30),
        nullable=False,
        default=HoldingValuationMethod.MARKET_PRICE.value,
        server_default=HoldingValuationMethod.MARKET_PRICE.value,
    )

    # Current price/value of one unit.
    #
    # IMPORTANT:
    #
    # This is LIVE/REFERENCE valuation data.
    #
    # It must NEVER overwrite:
    #
    #     total_cost_basis
    #     cost_basis_per_unit
    #
    # Example:
    #
    #     Historical acquisition price = $180
    #     Current market price         = $215
    #
    #     cost_basis_per_unit          = $180
    #     current_unit_price           = $215
    current_unit_price = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # Current total market/user-calculated value.
    #
    # Normally:
    #
    #     quantity × current_unit_price
    #
    # Currency conversion may be applied by the valuation
    # service when the asset and portfolio currencies differ.
    #
    # This value is a CURRENT VALUATION SNAPSHOT.
    #
    # It is NOT historical acquisition value.
    current_total_value = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # Currency of the current valuation.
    #
    # This may differ from cost_basis_currency.
    #
    # Example:
    #
    #     Cost basis = NGN
    #     Current valuation = USD
    #
    # The valuation layer is responsible for currency conversion
    # when required.
    valuation_currency = Column(
        String(3),
        nullable=True,
    )

    # Time at which the current valuation was obtained.
    price_updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # RECORD TIMESTAMPS
    # =========================================================

    # When the Holding record was created.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When the Holding record was last modified.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # Portfolio containing this holding.
    portfolio = relationship(
        "Portfolio",
        back_populates="holdings",
    )

    # Canonical asset represented by this holding.
    asset = relationship(
        "Asset",
        back_populates="holdings",
    )