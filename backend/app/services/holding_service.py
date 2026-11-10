from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from backend.app.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.asset import Asset
from backend.app.models.holding import Holding, HoldingValuationMethod
from backend.app.models.portfolio import Portfolio
from backend.app.schemas.holding import HoldingValuationUpdate
from backend.app.services.base_service import BaseService
from sqlalchemy import select
from sqlalchemy.orm import Session


class HoldingService(BaseService[Holding]):
    """
    Provides ownership-aware access to portfolio holdings.

    Responsibilities:
        - Retrieve holdings belonging to a user's portfolios.
        - List holdings belonging to a user.
        - Update permitted manual valuation information.

    Excluded responsibilities:
        - Creating ordinary holdings.
        - Deleting holdings.
        - Changing current quantity.
        - Changing historical cost basis.
        - Updating market prices directly.

    Transaction processing owns position changes.
    Market-data infrastructure owns market-price updates.
    """

    model = Holding

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def get_holding(
        self,
        user_id: int,
        holding_id: int,
    ) -> Holding | None:
        """
        Retrieve a holding only if its portfolio belongs to the user.

        Inactive portfolios remain visible for historical reporting.
        """

        self._validate_user_id(user_id)
        self._validate_record_id(holding_id, "holding_id")

        statement = (
            select(Holding)
            .join(
                Portfolio,
                Holding.portfolio_id == Portfolio.id,
            )
            .where(
                Holding.id == holding_id,
                Portfolio.user_id == user_id,
            )
        )

        return self.db.scalar(statement)

    def require_holding(
        self,
        user_id: int,
        holding_id: int,
    ) -> Holding:
        """
        Retrieve an owned holding or raise NotFoundError.

        A missing holding and a holding belonging to another user
        produce the same response to avoid disclosing its existence.
        """

        holding = self.get_holding(user_id, holding_id)

        if holding is None:
            raise NotFoundError("Holding was not found.")

        return holding

    def list_holdings(
        self,
        user_id: int,
        *,
        portfolio_id: int | None = None,
    ) -> list[Holding]:
        """
        List all holdings belonging to a user.

        When portfolio_id is supplied, the portfolio must belong
        to the user and be active.
        """

        self._validate_user_id(user_id)

        statement = (
            select(Holding)
            .join(
                Portfolio,
                Holding.portfolio_id == Portfolio.id,
            )
            .where(Portfolio.user_id == user_id)
            .order_by(Holding.id.asc())
        )

        if portfolio_id is not None:
            self._validate_record_id(portfolio_id, "portfolio_id")

            portfolio = self._resolve_portfolio(
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            if not cast(bool, portfolio.is_active):
                raise ConflictError(
                    "Holdings cannot be listed through an inactive portfolio."
                )

            statement = statement.where(
                Holding.portfolio_id == portfolio_id
            )

        return list(self.db.scalars(statement).all())

    # =========================================================
    # MANUAL VALUATION
    # =========================================================

    def update_valuation(
        self,
        user_id: int,
        holding_id: int,
        data: HoldingValuationUpdate,
    ) -> Holding:
        """
        Update the valuation of a manually valued holding.

        This operation never changes:
            - Quantity.
            - Ownership percentage.
            - Historical cost basis.

        Market-backed valuations belong to the market-data
        infrastructure, not this service.
        """

        self._validate_user_id(user_id)

        holding = self.require_holding(
            user_id=user_id,
            holding_id=holding_id,
        )

        portfolio = self._resolve_portfolio(
            user_id=user_id,
            portfolio_id=cast(int, holding.portfolio_id),
        )

        asset = self._resolve_asset(
            asset_id=cast(int, holding.asset_id),
        )

        # Prevent valuation changes through inactive resources.
        if not cast(bool, portfolio.is_active):
            raise ConflictError(
                "Valuation cannot be updated in an inactive portfolio."
            )

        if not cast(bool, asset.is_active):
            raise ConflictError(
                "Valuation cannot be updated for an inactive asset."
            )

        # Only manually valued assets may use this operation.
        is_market_backed = cast(bool, asset.is_market_backed)
        asset_valuation_method = cast(str, asset.valuation_method)

        if is_market_backed or asset_valuation_method != "MANUAL":
            raise ValidationError(
                "This asset requires market-data valuation."
            )

        quantity = cast(Decimal, holding.quantity)

        if data.current_unit_price is not None:
            # Calculate the total from the supplied unit price.
            calculated_total = quantity * data.current_unit_price

            # If both values were supplied, they must agree.
            if (
                data.current_total_value is not None
                and data.current_total_value != calculated_total
            ):
                raise ValidationError(
                    "current_total_value must equal quantity multiplied "
                    "by current_unit_price."
                )

            holding.current_unit_price = data.current_unit_price
            holding.current_total_value = calculated_total

        else:
            # A total-only valuation cannot establish a reliable
            # unit price, so clear any previously stored unit price.
            holding.current_unit_price = None
            holding.current_total_value = data.current_total_value

        # The service controls the valuation method.
        # The caller cannot choose MARKET_PRICE or CALCULATED.
        holding.valuation_method = (
            HoldingValuationMethod.USER_VALUED.value
        )

        holding.valuation_currency = data.valuation_currency
        holding.price_updated_at = datetime.now(timezone.utc)

        # BaseService commits and refreshes the supplied record.
        self.commit(holding)

        return holding

    # =========================================================
    # RESOURCE RESOLUTION
    # =========================================================

    def _resolve_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
    ) -> Portfolio:
        """Resolve a portfolio while enforcing user ownership."""

        statement = select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == user_id,
        )

        portfolio = self.db.scalar(statement)

        if portfolio is None:
            raise NotFoundError("Portfolio was not found.")

        return portfolio

    def _resolve_asset(self, asset_id: int) -> Asset:
        """Resolve the canonical asset referenced by a holding."""

        asset = self.db.get(Asset, asset_id)

        if asset is None:
            raise NotFoundError("Asset was not found.")

        return asset

    # =========================================================
    # INPUT VALIDATION
    # =========================================================

    @staticmethod
    def _validate_user_id(user_id: int) -> None:
        """Reject invalid authenticated user identifiers."""
        if type(user_id) is not int or user_id <= 0:
            raise ValidationError("A valid user_id is required.")


    @staticmethod
    def _validate_record_id(
        record_id: int,
        field_name: str,
    ) -> None:
        """Reject invalid database record identifiers."""

        if type(record_id) is not int or record_id <= 0:
            raise ValidationError(
                f"{field_name} must be a positive integer."
            )