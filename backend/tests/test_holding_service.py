
from decimal import Decimal

import pytest
from backend.app.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.asset import Asset
from backend.app.models.holding import Holding, HoldingValuationMethod
from backend.app.models.portfolio import Portfolio
from backend.app.models.user import User
from backend.app.schemas.holding import HoldingValuationUpdate
from backend.app.services.holding_service import HoldingService
from sqlalchemy.orm import Session

# ============================================================
# TEST DATA HELPERS
# ============================================================


def create_user(
    db: Session,
    *,
    email: str = "holding-test@example.com",
) -> User:
    """Create a user for a HoldingService integration test."""

    user = User(
        email=email,
        password_hash="test-password-hash",
        is_active=True,
    )

    db.add(user)
    db.flush()

    return user


def create_portfolio(
    db: Session,
    user: User,
    *,
    name: str = "Test Portfolio",
    is_active: bool = True,
) -> Portfolio:
    """Create a portfolio belonging to the supplied user."""

    portfolio = Portfolio(
        user_id=user.id,
        name=name,
        is_active=is_active,
    )

    db.add(portfolio)
    db.flush()

    return portfolio


def create_asset(
    db: Session,
    *,
    name: str = "Physical Gold",
    is_market_backed: bool = False,
    valuation_method: str = "MANUAL",
) -> Asset:
    """Create a canonical asset with the requested valuation type."""

    asset = Asset(
        name=name,
        asset_type="COMMODITY",
        pricing_currency="NGN",
        unit="GRAM",
        is_market_backed=is_market_backed,
        valuation_method=valuation_method,
        is_active=True,
    )

    db.add(asset)
    db.flush()

    return asset


def create_holding(
    db: Session,
    portfolio: Portfolio,
    asset: Asset,
    *,
    quantity: Decimal = Decimal(10),
    total_cost_basis: Decimal = Decimal(1000),
    cost_basis_per_unit: Decimal = Decimal(100),
) -> Holding:
    """Create a holding with an existing position and cost basis."""

    valuation_method = (
        HoldingValuationMethod.MARKET_PRICE.value
        if asset.valuation_method == "MARKET"
        else HoldingValuationMethod.USER_VALUED.value
    )

    holding = Holding(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        quantity=quantity,
        ownership_percentage=None,
        total_cost_basis=total_cost_basis,
        cost_basis_per_unit=cost_basis_per_unit,
        cost_basis_currency="NGN",
        valuation_method=valuation_method,
        current_unit_price=None,
        current_total_value=None,
        valuation_currency=None,
        price_updated_at=None,
    )

    db.add(holding)
    db.flush()

    return holding


def create_manual_holding(
    db: Session,
    *,
    user_email: str = "holding-test@example.com",
    portfolio_name: str = "Test Portfolio",
    portfolio_active: bool = True,
    asset_active: bool = True,
) -> tuple[User, Portfolio, Asset, Holding]:
    """Create a complete user, portfolio, manual asset, and holding."""

    user = create_user(db, email=user_email)

    portfolio = create_portfolio(
        db,
        user,
        name=portfolio_name,
        is_active=portfolio_active,
    )

    asset = create_asset(db)

    if not asset_active:
        asset.is_active = False

    holding = create_holding(db, portfolio, asset)

    return user, portfolio, asset, holding


# ============================================================
# RETRIEVAL TESTS
# ============================================================


def test_get_holding_returns_users_own_holding(db: Session) -> None:
    """A user can retrieve a holding belonging to their portfolio."""

    user, _, _, holding = create_manual_holding(db)

    service = HoldingService(db)

    result = service.get_holding(user.id, holding.id)

    assert result is not None
    assert result.id == holding.id
    assert result.portfolio_id == holding.portfolio_id


def test_get_holding_returns_none_for_another_users_holding(
    db: Session,
) -> None:
    """A user cannot retrieve another user's holding."""

    first_user, _, _, first_holding = create_manual_holding(
        db,
        user_email="first-user@example.com",
    )

    second_user = create_user(
        db,
        email="second-user@example.com",
    )

    service = HoldingService(db)

    result = service.get_holding(
        second_user.id,
        first_holding.id,
    )

    assert first_user.id != second_user.id
    assert result is None


def test_require_holding_raises_for_another_users_holding(
    db: Session,
) -> None:
    """Cross-user access is reported as NotFoundError."""

    _, _, _, holding = create_manual_holding(
        db,
        user_email="owner@example.com",
    )

    other_user = create_user(
        db,
        email="other-user@example.com",
    )

    service = HoldingService(db)

    with pytest.raises(NotFoundError):
        service.require_holding(
            other_user.id,
            holding.id,
        )


def test_get_holding_allows_historical_inactive_portfolio(
    db: Session,
) -> None:
    """Inactive portfolios remain accessible for historical reporting."""

    user, _, _, holding = create_manual_holding(
        db,
        portfolio_active=False,
    )

    service = HoldingService(db)

    result = service.get_holding(user.id, holding.id)

    assert result is not None
    assert result.id == holding.id


# ============================================================
# LISTING TESTS
# ============================================================


def test_list_holdings_returns_all_users_holdings(
    db: Session,
) -> None:
    """Listing returns holdings across the user's portfolios."""

    user = create_user(db)

    first_portfolio = create_portfolio(
        db,
        user,
        name="First Portfolio",
    )

    second_portfolio = create_portfolio(
        db,
        user,
        name="Second Portfolio",
    )

    first_asset = create_asset(
        db,
        name="Physical Gold",
    )

    second_asset = create_asset(
        db,
        name="Physical Silver",
    )

    first_holding = create_holding(
        db,
        first_portfolio,
        first_asset,
    )

    second_holding = create_holding(
        db,
        second_portfolio,
        second_asset,
    )

    service = HoldingService(db)

    results = service.list_holdings(user.id)

    result_ids = {holding.id for holding in results}

    assert result_ids == {
        first_holding.id,
        second_holding.id,
    }


def test_list_holdings_can_filter_by_portfolio(
    db: Session,
) -> None:
    """A portfolio filter returns only that portfolio's holdings."""

    user = create_user(db)

    first_portfolio = create_portfolio(
        db,
        user,
        name="First Portfolio",
    )

    second_portfolio = create_portfolio(
        db,
        user,
        name="Second Portfolio",
    )

    first_asset = create_asset(db, name="Gold")
    second_asset = create_asset(db, name="Silver")

    first_holding = create_holding(
        db,
        first_portfolio,
        first_asset,
    )

    create_holding(
        db,
        second_portfolio,
        second_asset,
    )

    service = HoldingService(db)

    results = service.list_holdings(
        user.id,
        portfolio_id=first_portfolio.id,
    )

    assert len(results) == 1
    assert results[0] is first_holding


def test_list_holdings_rejects_another_users_portfolio(
    db: Session,
) -> None:
    """A user cannot list holdings through another user's portfolio."""

    # Create the user who owns the portfolio and holding.
    owner, _, _, _ = create_manual_holding(
        db,
        user_email="portfolio-owner@example.com",
    )

    # Create a different user who must not access that portfolio.
    other_user = create_user(
        db,
        email="portfolio-outsider@example.com",
    )

    # Retrieve the portfolio belonging to the original owner.
    portfolio = db.query(Portfolio).filter_by(
        user_id=owner.id,
    ).first()

    assert portfolio is not None

    service = HoldingService(db)

    # The second user must receive NotFoundError when trying
    # to list holdings belonging to the first user's portfolio.
    with pytest.raises(NotFoundError):
        service.list_holdings(
            other_user.id,
            portfolio_id=portfolio.id,
        )



def test_list_holdings_rejects_inactive_portfolio_filter(
    db: Session,
) -> None:
    """An inactive portfolio cannot be used as an active filter."""

    user, portfolio, _, _ = create_manual_holding(
        db,
        portfolio_active=False,
    )

    service = HoldingService(db)

    with pytest.raises(ConflictError):
        service.list_holdings(
            user.id,
            portfolio_id=portfolio.id,
        )


# ============================================================
# MANUAL VALUATION TESTS
# ============================================================


def test_update_manual_valuation_from_unit_price(
    db: Session,
) -> None:
    """Unit price updates calculate and persist the total value."""

    user, _, _, holding = create_manual_holding(db)

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(120),
        valuation_currency="ngn",
    )

    result = service.update_valuation(
        user.id,
        holding.id,
        data,
    )

    assert result.current_unit_price == Decimal(120)
    assert result.current_total_value == Decimal(1200)
    assert result.valuation_currency == "NGN"
    assert result.valuation_method == (
        HoldingValuationMethod.USER_VALUED.value
    )
    assert result.price_updated_at is not None


def test_update_manual_valuation_from_total_value_only(
    db: Session,
) -> None:
    """A total-only update clears the previously stored unit price."""

    user, _, _, holding = create_manual_holding(db)

    holding.current_unit_price = Decimal(100)
    holding.current_total_value = Decimal(1000)
    holding.valuation_currency = "NGN"

    db.flush()

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_total_value=Decimal(1500),
        valuation_currency="NGN",
    )

    result = service.update_valuation(
        user.id,
        holding.id,
        data,
    )

    assert result.current_unit_price is None
    assert result.current_total_value == Decimal(1500)
    assert result.valuation_currency == "NGN"


def test_update_manual_valuation_preserves_quantity_and_cost_basis(
    db: Session,
) -> None:
    """
    A valuation update must never alter the financial position
    or its historical acquisition information.
    """

    user, _, _, holding = create_manual_holding(db)

    original_quantity = holding.quantity
    original_total_cost_basis = holding.total_cost_basis
    original_cost_basis_per_unit = holding.cost_basis_per_unit
    original_cost_basis_currency = holding.cost_basis_currency

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(125),
        valuation_currency="NGN",
    )

    service.update_valuation(
        user.id,
        holding.id,
        data,
    )

    db.refresh(holding)

    assert holding.quantity == original_quantity
    assert holding.total_cost_basis == original_total_cost_basis
    assert holding.cost_basis_per_unit == original_cost_basis_per_unit
    assert holding.cost_basis_currency == original_cost_basis_currency


def test_update_manual_valuation_rejects_inconsistent_values(
    db: Session,
) -> None:
    """A supplied total must agree with quantity multiplied by price."""

    user, _, _, holding = create_manual_holding(db)

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(100),
        current_total_value=Decimal(2000),
        valuation_currency="NGN",
    )

    with pytest.raises(ValidationError):
        service.update_valuation(
            user.id,
            holding.id,
            data,
        )


def test_update_manual_valuation_rejects_inactive_portfolio(
    db: Session,
) -> None:
    """Manual valuations cannot be updated in inactive portfolios."""

    user, _, _, holding = create_manual_holding(
        db,
        portfolio_active=False,
    )

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(120),
        valuation_currency="NGN",
    )

    with pytest.raises(ConflictError):
        service.update_valuation(
            user.id,
            holding.id,
            data,
        )


def test_update_manual_valuation_rejects_inactive_asset(
    db: Session,
) -> None:
    """Manual valuations cannot be updated for inactive assets."""

    user, _, _, holding = create_manual_holding(
        db,
        asset_active=False,
    )

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(120),
        valuation_currency="NGN",
    )

    with pytest.raises(ConflictError):
        service.update_valuation(
            user.id,
            holding.id,
            data,
        )


def test_update_manual_valuation_rejects_market_backed_asset(
    db: Session,
) -> None:
    """Market-backed assets cannot use the manual valuation operation."""

    user = create_user(db)

    portfolio = create_portfolio(
        db,
        user,
    )

    asset = create_asset(
        db,
        name="Bitcoin",
        is_market_backed=True,
        valuation_method="MARKET",
    )

    holding = create_holding(
        db,
        portfolio,
        asset,
    )

    service = HoldingService(db)

    data = HoldingValuationUpdate(
        current_unit_price=Decimal(100000),
        valuation_currency="USD",
    )

    with pytest.raises(ValidationError):
        service.update_valuation(
            user.id,
            holding.id,
            data,
        )


# ============================================================
# INPUT VALIDATION TESTS
# ============================================================


@pytest.mark.parametrize(
    "user_id",
    [0, -1, True],
)
def test_get_holding_rejects_invalid_user_id(
    db: Session,
    user_id: int,
) -> None:
    """Invalid user identifiers are rejected."""

    service = HoldingService(db)

    with pytest.raises(ValidationError):
        service.get_holding(user_id, 1)


@pytest.mark.parametrize(
    "holding_id",
    [0, -1, True],
)
def test_get_holding_rejects_invalid_holding_id(
    db: Session,
    holding_id: int,
) -> None:
    """Invalid holding identifiers are rejected."""

    user = create_user(db)

    service = HoldingService(db)

    with pytest.raises(ValidationError):
        service.get_holding(user.id, holding_id)
