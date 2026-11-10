from enum import Enum

from backend.app.database.connection import Base
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

# ============================================================
# ENUMS
# ============================================================


class HoldingValuationMethod(str, Enum):
    """How Finova obtains a holding's current valuation."""

    MARKET_PRICE = "MARKET_PRICE"
    USER_VALUED = "USER_VALUED"


# ============================================================
# MODEL
# ============================================================


class Holding(Base):
    """
    Represents the current position in an asset within a portfolio.

    Asset defines the canonical identity and measurement unit.
    Holding records the quantity owned in that canonical unit.

    For example:
        Asset.unit = "GRAM"
        Holding.quantity = 500

    If a user enters 0.5 kilograms, the unit-conversion layer
    must convert that quantity to 500 grams before updating
    the Holding.

    Historical acquisition information and current valuation
    are deliberately stored separately.

    Quantity and cost basis are maintained by transaction
    processing or controlled opening-balance/import workflows.
    """

    __tablename__ = "holdings"

    # ========================================================
    # INDEXES AND DATABASE CONSTRAINTS
    # ========================================================

    __table_args__ = (
        # One position per asset in each portfolio.
        Index(
            "uq_holdings_portfolio_asset",
            "portfolio_id",
            "asset_id",
            unique=True,
        ),

        # Supports lookups of portfolios holding a particular asset.
        Index(
            "ix_holdings_asset_id",
            "asset_id",
        ),

        CheckConstraint(
            "quantity >= 0",
            name="ck_holdings_quantity_non_negative",
        ),

        CheckConstraint(
            "total_cost_basis >= 0",
            name="ck_holdings_total_cost_basis_non_negative",
        ),

        CheckConstraint(
            "cost_basis_per_unit >= 0",
            name="ck_holdings_cost_basis_per_unit_non_negative",
        ),

        CheckConstraint(
            "current_unit_price IS NULL OR current_unit_price >= 0",
            name="ck_holdings_current_unit_price_non_negative",
        ),

        CheckConstraint(
            "current_total_value IS NULL OR current_total_value >= 0",
            name="ck_holdings_current_total_value_non_negative",
        ),

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

        # Only valuation methods currently supported by Finova.
        CheckConstraint(
            "valuation_method IN ('MARKET_PRICE', 'USER_VALUED')",
            name="ck_holdings_valuation_method",
        ),

        # A stored valuation amount must have an associated currency.
        CheckConstraint(
            """
            (
                current_unit_price IS NULL
                AND current_total_value IS NULL
            )
            OR valuation_currency IS NOT NULL
            """,
            name="ck_holdings_valuation_currency_required",
        ),
    )

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id = Column(
        Integer,
        primary_key=True,
    )

    # ========================================================
    # PORTFOLIO AND ASSET
    # ========================================================

    portfolio_id = Column(
        Integer,
        ForeignKey(
            "portfolios.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    asset_id = Column(
        Integer,
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # ========================================================
    # CURRENT POSITION
    # ========================================================

    # Always expressed in the canonical unit defined by Asset.unit.
    #
    # This is the current position, not the original purchase quantity.
    quantity = Column(
        Numeric(20, 8),
        nullable=False,
    )

    # ========================================================
    # OWNERSHIP-BASED ASSETS
    # ========================================================

    # Relevant to businesses, partnerships, and similar assets.
    #
    # This is separate from quantity. For example, a holding
    # may represent one business with a 25% ownership interest.
    ownership_percentage = Column(
        Numeric(7, 4),
        nullable=True,
    )

    # ========================================================
    # HISTORICAL COST BASIS
    # ========================================================

    # Remaining historical acquisition cost represented by
    # the current position.
    #
    # Market-price changes must never modify this field.
    total_cost_basis = Column(
        Numeric(20, 8),
        nullable=False,
        default=0,
        server_default="0",
    )

    # Average historical acquisition cost per canonical unit.
    #
    # Maintained by transaction/position processing.
    cost_basis_per_unit = Column(
        Numeric(20, 8),
        nullable=False,
        default=0,
        server_default="0",
    )

    cost_basis_currency = Column(
        String(3),
        nullable=False,
    )

    # ========================================================
    # CURRENT VALUATION
    # ========================================================

    valuation_method = Column(
        String(30),
        nullable=False,
    )

    # Current value of one canonical unit.
    current_unit_price = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # Current total valuation snapshot.
    #
    # For a unit-priced asset, this is normally:
    # quantity × current_unit_price.
    #
    # Currency conversion and valuation policy belong to the
    # valuation layer, not to this database model.
    current_total_value = Column(
        Numeric(20, 8),
        nullable=True,
    )

    valuation_currency = Column(
        String(3),
        nullable=True,
    )

    price_updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ========================================================
    # RECORD TIMESTAMPS
    # ========================================================

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

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    portfolio = relationship(
        "Portfolio",
        back_populates="holdings",
    )

    asset = relationship(
        "Asset",
        back_populates="holdings",
    )