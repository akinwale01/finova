from decimal import Decimal
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.holding import (
    HoldingCreate,
    HoldingListResponse,
    HoldingRead,
    HoldingUpdate,
    ValuationMethod,
)


# ============================================================
# HOLDING CREATE
# ============================================================


def valid_holding_create_data() -> dict:
    return {
        "portfolio_id": 1,
        "asset_id": 1,
        "quantity": "10.00000000",
        "unit": "shares",
        "total_cost_basis": "1500.00000000",
        "cost_basis_per_unit": "150.00000000",
        "cost_basis_currency": "usd",
        "valuation_method": "market_price",
        "current_unit_price": "175.00000000",
        "current_total_value": "1750.00000000",
        "valuation_currency": "usd",
    }


def test_holding_create_valid():
    holding = HoldingCreate(**valid_holding_create_data())

    assert holding.portfolio_id == 1
    assert holding.asset_id == 1
    assert holding.quantity == Decimal("10.00000000")
    assert holding.unit == "shares"

    assert holding.total_cost_basis == Decimal("1500.00000000")
    assert holding.cost_basis_per_unit == Decimal("150.00000000")

    assert holding.cost_basis_currency == "USD"
    assert holding.valuation_currency == "USD"

    assert holding.valuation_method == ValuationMethod.MARKET_PRICE


def test_holding_create_normalizes_currency():
    data = valid_holding_create_data()

    data["cost_basis_currency"] = " ngn "
    data["valuation_currency"] = " usd "

    holding = HoldingCreate(**data)

    assert holding.cost_basis_currency == "NGN"
    assert holding.valuation_currency == "USD"


def test_holding_create_rejects_zero_portfolio_id():
    data = valid_holding_create_data()
    data["portfolio_id"] = 0

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_portfolio_id():
    data = valid_holding_create_data()
    data["portfolio_id"] = -1

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_zero_asset_id():
    data = valid_holding_create_data()
    data["asset_id"] = 0

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_quantity():
    data = valid_holding_create_data()
    data["quantity"] = "-1"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_allows_zero_quantity():
    data = valid_holding_create_data()
    data["quantity"] = "0"

    holding = HoldingCreate(**data)

    assert holding.quantity == Decimal("0")


def test_holding_create_rejects_negative_cost_basis():
    data = valid_holding_create_data()
    data["total_cost_basis"] = "-100"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_cost_basis_per_unit():
    data = valid_holding_create_data()
    data["cost_basis_per_unit"] = "-10"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_invalid_cost_basis_currency():
    data = valid_holding_create_data()
    data["cost_basis_currency"] = "US"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_numeric_currency():
    data = valid_holding_create_data()
    data["cost_basis_currency"] = "123"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# OWNERSHIP PERCENTAGE
# ============================================================


def test_holding_create_accepts_valid_ownership_percentage():
    data = valid_holding_create_data()
    data["ownership_percentage"] = "25.5000"

    holding = HoldingCreate(**data)

    assert holding.ownership_percentage == Decimal("25.5000")


def test_holding_create_accepts_zero_ownership_percentage():
    data = valid_holding_create_data()
    data["ownership_percentage"] = "0"

    holding = HoldingCreate(**data)

    assert holding.ownership_percentage == Decimal("0")


def test_holding_create_accepts_100_ownership_percentage():
    data = valid_holding_create_data()
    data["ownership_percentage"] = "100"

    holding = HoldingCreate(**data)

    assert holding.ownership_percentage == Decimal("100")


def test_holding_create_rejects_ownership_above_100():
    data = valid_holding_create_data()
    data["ownership_percentage"] = "100.0001"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_ownership():
    data = valid_holding_create_data()
    data["ownership_percentage"] = "-0.01"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# VALUATION
# ============================================================


def test_holding_create_allows_missing_current_valuation():
    data = valid_holding_create_data()

    data["current_unit_price"] = None
    data["current_total_value"] = None
    data["valuation_currency"] = None

    holding = HoldingCreate(**data)

    assert holding.current_unit_price is None
    assert holding.current_total_value is None
    assert holding.valuation_currency is None


def test_holding_create_requires_currency_for_unit_price():
    data = valid_holding_create_data()

    data["current_unit_price"] = "100"
    data["valuation_currency"] = None

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_requires_currency_for_total_value():
    data = valid_holding_create_data()

    data["current_total_value"] = "1000"
    data["valuation_currency"] = None

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_current_unit_price():
    data = valid_holding_create_data()
    data["current_unit_price"] = "-1"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_current_total_value():
    data = valid_holding_create_data()
    data["current_total_value"] = "-1"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# UNIT VALIDATION
# ============================================================


def test_holding_create_strips_unit():
    data = valid_holding_create_data()
    data["unit"] = " shares "

    holding = HoldingCreate(**data)

    assert holding.unit == "shares"


def test_holding_create_rejects_blank_unit():
    data = valid_holding_create_data()
    data["unit"] = "   "

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# ENUM VALIDATION
# ============================================================


@pytest.mark.parametrize(
    "valuation_method",
    [
        "market_price",
        "user_valued",
        "calculated",
    ],
)
def test_holding_create_accepts_valid_valuation_methods(
    valuation_method,
):
    data = valid_holding_create_data()
    data["valuation_method"] = valuation_method

    holding = HoldingCreate(**data)

    assert holding.valuation_method.value == valuation_method


def test_holding_create_rejects_invalid_valuation_method():
    data = valid_holding_create_data()
    data["valuation_method"] = "invalid_method"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# HOLDING UPDATE
# ============================================================


def test_holding_update_accepts_valid_data():
    holding = HoldingUpdate(
        quantity="20",
        unit="BTC",
        valuation_method="market_price",
        current_unit_price="100000",
        valuation_currency="USD",
    )

    assert holding.quantity == Decimal("20")
    assert holding.unit == "BTC"
    assert holding.valuation_method == ValuationMethod.MARKET_PRICE


def test_holding_update_allows_empty_partial_update():
    holding = HoldingUpdate()

    assert holding.model_dump(exclude_unset=True) == {}


def test_holding_update_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        HoldingUpdate(quantity="-1")


def test_holding_update_rejects_negative_current_price():
    with pytest.raises(ValidationError):
        HoldingUpdate(current_unit_price="-1")


def test_holding_update_rejects_negative_total_value():
    with pytest.raises(ValidationError):
        HoldingUpdate(current_total_value="-1")


def test_holding_update_rejects_invalid_ownership_percentage():
    with pytest.raises(ValidationError):
        HoldingUpdate(ownership_percentage="101")


def test_holding_update_normalizes_currency():
    holding = HoldingUpdate(
        valuation_currency=" ngn ",
    )

    assert holding.valuation_currency == "NGN"


def test_holding_update_rejects_blank_unit():
    with pytest.raises(ValidationError):
        HoldingUpdate(unit="   ")


# ============================================================
# PROTECTED HISTORICAL FIELDS
# ============================================================


@pytest.mark.parametrize(
    "field",
    [
        "total_cost_basis",
        "cost_basis_per_unit",
        "cost_basis_currency",
        "portfolio_id",
        "asset_id",
    ],
)
def test_holding_update_rejects_protected_fields(field):
    with pytest.raises(ValidationError):
        HoldingUpdate(**{field: 100})


# ============================================================
# HOLDING READ
# ============================================================


def test_holding_read_from_attributes():
    class HoldingObject:
        id = 1
        portfolio_id = 2
        asset_id = 3
        quantity = Decimal("10")
        unit = "shares"
        ownership_percentage = None
        valuation_method = ValuationMethod.MARKET_PRICE
        current_unit_price = Decimal("200")
        current_total_value = Decimal("2000")
        price_updated_at = datetime.now(timezone.utc)

        total_cost_basis = Decimal("1500")
        cost_basis_per_unit = Decimal("150")

        cost_basis_currency = "USD"
        valuation_currency = "USD"

        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

    holding = HoldingRead.model_validate(HoldingObject())

    assert holding.id == 1
    assert holding.portfolio_id == 2
    assert holding.asset_id == 3

    assert holding.quantity == Decimal("10")
    assert holding.total_cost_basis == Decimal("1500")
    assert holding.cost_basis_per_unit == Decimal("150")

    assert holding.cost_basis_currency == "USD"
    assert holding.valuation_currency == "USD"


# ============================================================
# LIST RESPONSE
# ============================================================


def test_holding_list_response():
    now = datetime.now(timezone.utc)

    holding = HoldingRead(
        id=1,
        portfolio_id=1,
        asset_id=1,
        quantity=Decimal("10"),
        unit="shares",
        ownership_percentage=None,
        valuation_method=ValuationMethod.MARKET_PRICE,
        current_unit_price=Decimal("200"),
        current_total_value=Decimal("2000"),
        price_updated_at=now,
        total_cost_basis=Decimal("1500"),
        cost_basis_per_unit=Decimal("150"),
        cost_basis_currency="USD",
        valuation_currency="USD",
        created_at=now,
        updated_at=now,
    )

    response = HoldingListResponse(
        items=[holding],
        total=1,
    )

    assert response.total == 1
    assert len(response.items) == 1


def test_holding_list_response_rejects_negative_total():
    with pytest.raises(ValidationError):
        HoldingListResponse(
            items=[],
            total=-1,
        )


# ============================================================
# EXTRA FIELDS
# ============================================================


def test_holding_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        HoldingUpdate(
            quantity="10",
            unknown_field="something",
        )