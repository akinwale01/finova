from datetime import datetime, timezone
from decimal import Decimal

import pytest
from backend.app.schemas.holding import (
    HoldingCreate,
    HoldingListResponse,
    HoldingRead,
    HoldingUpdate,
    HoldingValuationUpdate,
    ValuationMethod,
)
from pydantic import ValidationError

# ============================================================
# TEST DATA
# ============================================================


def valid_holding_create_data() -> dict[str, int | str]:
    """Return valid data for creating an initial holding position."""

    return {
        "portfolio_id": 1,
        "asset_id": 1,
        "quantity": "10.00000000",
        "total_cost_basis": "1500.00000000",
        "cost_basis_per_unit": "150.00000000",
        "cost_basis_currency": "USD",
        "valuation_method": "MARKET_PRICE",
        "current_unit_price": "175.00000000",
        "current_total_value": "1750.00000000",
        "valuation_currency": "USD",
    }


# ============================================================
# HOLDING CREATE
# ============================================================


def test_holding_create_valid() -> None:
    holding = HoldingCreate(**valid_holding_create_data())

    assert holding.portfolio_id == 1
    assert holding.asset_id == 1
    assert holding.quantity == Decimal("10.00000000")

    assert holding.total_cost_basis == Decimal("1500.00000000")
    assert holding.cost_basis_per_unit == Decimal("150.00000000")

    assert holding.cost_basis_currency == "USD"
    assert holding.valuation_currency == "USD"

    assert holding.valuation_method == ValuationMethod.MARKET_PRICE


def test_holding_create_normalizes_currency() -> None:
    data = valid_holding_create_data()
    data["cost_basis_currency"] = " ngn "
    data["valuation_currency"] = " usd "

    holding = HoldingCreate(**data)

    assert holding.cost_basis_currency == "NGN"
    assert holding.valuation_currency == "USD"


@pytest.mark.parametrize("field", ["portfolio_id", "asset_id"])
@pytest.mark.parametrize("invalid_id", [0, -1])
def test_holding_create_rejects_invalid_ids(
    field: str,
    invalid_id: int,
) -> None:
    data = valid_holding_create_data()
    data[field] = invalid_id

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_quantity() -> None:
    data = valid_holding_create_data()
    data["quantity"] = "-1"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_zero_quantity() -> None:
    data = valid_holding_create_data()
    data["quantity"] = "0"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_cost_basis() -> None:
    data = valid_holding_create_data()
    data["total_cost_basis"] = "-100"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_negative_cost_basis_per_unit() -> None:
    data = valid_holding_create_data()
    data["cost_basis_per_unit"] = "-10"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


@pytest.mark.parametrize(
    "currency",
    ["US", "123", "", "USDD"],
)
def test_holding_create_rejects_invalid_cost_basis_currency(
    currency: str,
) -> None:
    data = valid_holding_create_data()
    data["cost_basis_currency"] = currency

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_inconsistent_cost_basis() -> None:
    data = valid_holding_create_data()
    data["cost_basis_per_unit"] = "200"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# OWNERSHIP PERCENTAGE
# ============================================================


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        ("25.5000", Decimal("25.5000")),
        ("0", Decimal(0)),
        ("100", Decimal(100)),
    ],
)
def test_holding_create_accepts_valid_ownership_percentage(
    percentage: str,
    expected: Decimal,
) -> None:
    data = valid_holding_create_data()
    data["ownership_percentage"] = percentage

    holding = HoldingCreate(**data)

    assert holding.ownership_percentage == expected


@pytest.mark.parametrize(
    "percentage",
    ["100.0001", "-0.01"],
)
def test_holding_create_rejects_invalid_ownership_percentage(
    percentage: str,
) -> None:
    data = valid_holding_create_data()
    data["ownership_percentage"] = percentage

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# HOLDING CREATE VALUATION
# ============================================================


def test_holding_create_allows_missing_current_valuation() -> None:
    data = valid_holding_create_data()
    data["current_unit_price"] = None
    data["current_total_value"] = None
    data["valuation_currency"] = None

    holding = HoldingCreate(**data)

    assert holding.current_unit_price is None
    assert holding.current_total_value is None
    assert holding.valuation_currency is None


@pytest.mark.parametrize(
    ("price_field", "price_value"),
    [
        ("current_unit_price", "100"),
        ("current_total_value", "1000"),
    ],
)
def test_holding_create_requires_currency_for_valuation(
    price_field: str,
    price_value: str,
) -> None:
    data = valid_holding_create_data()
    data[price_field] = price_value
    data["valuation_currency"] = None

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


@pytest.mark.parametrize(
    ("price_field", "price_value"),
    [
        ("current_unit_price", "-1"),
        ("current_total_value", "-1"),
    ],
)
def test_holding_create_rejects_negative_valuation(
    price_field: str,
    price_value: str,
) -> None:
    data = valid_holding_create_data()
    data[price_field] = price_value

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


def test_holding_create_rejects_inconsistent_valuation() -> None:
    data = valid_holding_create_data()
    data["current_total_value"] = "2000"

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# VALUATION METHOD
# ============================================================


@pytest.mark.parametrize(
    "valuation_method",
    [
        "MARKET_PRICE",
        "USER_VALUED",
    ],
)
def test_holding_create_accepts_valid_valuation_methods(
    valuation_method: str,
) -> None:
    data = valid_holding_create_data()
    data["valuation_method"] = valuation_method

    holding = HoldingCreate(**data)

    assert holding.valuation_method.value == valuation_method


@pytest.mark.parametrize(
    "valuation_method",
    [
        "CALCULATED",
        "MANUAL",
        "invalid_method",
    ],
)
def test_holding_create_rejects_unsupported_valuation_methods(
    valuation_method: str,
) -> None:
    data = valid_holding_create_data()
    data["valuation_method"] = valuation_method

    with pytest.raises(ValidationError):
        HoldingCreate(**data)


# ============================================================
# HOLDING UPDATE
# ============================================================


def test_holding_update_accepts_ownership_percentage() -> None:
    holding = HoldingUpdate(
        ownership_percentage=Decimal("25.5000"),
    )

    assert holding.ownership_percentage == Decimal("25.5000")


def test_holding_update_rejects_empty_update() -> None:
    with pytest.raises(ValidationError):
        HoldingUpdate()


@pytest.mark.parametrize(
    "percentage",
    [
        Decimal("-0.01"),
        Decimal("100.0001"),
    ],
)
def test_holding_update_rejects_invalid_ownership_percentage(
    percentage: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        HoldingUpdate(ownership_percentage=percentage)


@pytest.mark.parametrize(
    "field",
    [
        "quantity",
        "total_cost_basis",
        "cost_basis_per_unit",
        "cost_basis_currency",
        "portfolio_id",
        "asset_id",
        "unit",
        "valuation_method",
        "current_unit_price",
        "current_total_value",
        "valuation_currency",
    ],
)
def test_holding_update_rejects_protected_or_unsupported_fields(
    field: str,
) -> None:
    with pytest.raises(ValidationError):
        HoldingUpdate.model_validate({field: 100})


def test_holding_update_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        HoldingUpdate.model_validate(
            {
                "ownership_percentage": "25",
                "unknown_field": "something",
            }
        )


# ============================================================
# HOLDING VALUATION UPDATE
# ============================================================


def test_holding_valuation_update_accepts_unit_price() -> None:
    valuation = HoldingValuationUpdate(
        current_unit_price=Decimal(175),
        valuation_currency=" usd ",
    )

    assert valuation.current_unit_price == Decimal(175)
    assert valuation.valuation_currency == "USD"


def test_holding_valuation_update_accepts_total_value_only() -> None:
    valuation = HoldingValuationUpdate(
        current_total_value=Decimal(1750),
        valuation_currency="NGN",
    )

    assert valuation.current_total_value == Decimal(1750)
    assert valuation.current_unit_price is None


def test_holding_valuation_update_requires_a_valuation_amount() -> None:
    with pytest.raises(ValidationError):
        HoldingValuationUpdate(
            valuation_currency="USD",
        )


def test_holding_valuation_update_requires_currency() -> None:
    with pytest.raises(ValidationError):
        HoldingValuationUpdate(
            current_unit_price=Decimal(175),
            valuation_currency=None,
        )


@pytest.mark.parametrize(
    "field",
    [
        "current_unit_price",
        "current_total_value",
    ],
)
def test_holding_valuation_update_rejects_negative_amounts(
    field: str,
) -> None:
    with pytest.raises(ValidationError):
        HoldingValuationUpdate.model_validate(
            {
                field: "-1",
                "valuation_currency": "USD",
            }
        )


def test_holding_valuation_update_normalizes_currency() -> None:
    valuation = HoldingValuationUpdate(
        current_total_value=Decimal(1000),
        valuation_currency=" ngn ",
    )

    assert valuation.valuation_currency == "NGN"


def test_holding_valuation_update_rejects_invalid_currency() -> None:
    with pytest.raises(ValidationError):
        HoldingValuationUpdate(
            current_total_value=Decimal(1000),
            valuation_currency="123",
        )


def test_holding_valuation_update_rejects_valuation_method() -> None:
    with pytest.raises(ValidationError):
        HoldingValuationUpdate.model_validate(
            {
                "current_unit_price": "175",
                "valuation_currency": "USD",
                "valuation_method": "MARKET_PRICE",
            }
        )


# ============================================================
# HOLDING READ
# ============================================================


def test_holding_read_from_attributes() -> None:
    now = datetime.now(timezone.utc)

    class HoldingObject:
        id = 1
        portfolio_id = 2
        asset_id = 3
        quantity = Decimal(10)
        ownership_percentage = None
        valuation_method = ValuationMethod.MARKET_PRICE
        current_unit_price = Decimal(200)
        current_total_value = Decimal(2000)
        price_updated_at = now
        total_cost_basis = Decimal(1500)
        cost_basis_per_unit = Decimal(150)
        cost_basis_currency = "USD"
        valuation_currency = "USD"
        created_at = now
        updated_at = now

    holding = HoldingRead.model_validate(HoldingObject())

    assert holding.id == 1
    assert holding.portfolio_id == 2
    assert holding.asset_id == 3
    assert holding.quantity == Decimal(10)
    assert holding.total_cost_basis == Decimal(1500)
    assert holding.cost_basis_per_unit == Decimal(150)
    assert holding.cost_basis_currency == "USD"
    assert holding.valuation_currency == "USD"


# ============================================================
# HOLDING LIST RESPONSE
# ============================================================


def test_holding_list_response() -> None:
    now = datetime.now(timezone.utc)

    holding = HoldingRead(
        id=1,
        portfolio_id=1,
        asset_id=1,
        quantity=Decimal(10),
        ownership_percentage=None,
        valuation_method=ValuationMethod.MARKET_PRICE,
        current_unit_price=Decimal(200),
        current_total_value=Decimal(2000),
        price_updated_at=now,
        total_cost_basis=Decimal(1500),
        cost_basis_per_unit=Decimal(150),
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


def test_holding_list_response_rejects_negative_total() -> None:
    with pytest.raises(ValidationError):
        HoldingListResponse(
            items=[],
            total=-1,
        )
