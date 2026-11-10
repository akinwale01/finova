from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.app.exceptions.common import ConflictError, NotFoundError, ValidationError
from backend.app.models.account import Account
from backend.app.models.asset import Asset
from backend.app.models.portfolio import Portfolio
from backend.app.models.transaction import TransactionStatus, TransactionType
from backend.app.schemas.transaction import TransactionCreate, TransactionUpdate
from backend.app.services.transaction_service import TransactionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_user(db, email="user@example.com"):
    from backend.app.models.user import User

    user = User(
        email=email,
        password_hash="hashed-password",
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_account(
    db,
    user_id,
    name="Test Account",
    account_type="BANK",
    currency="USD",
    is_active=True,
):
    account = Account(
        user_id=user_id,
        name=name,
        account_type=account_type,
        currency=currency,
        is_active=is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def create_portfolio(
    db,
    user_id,
    name="Test Portfolio",
    is_active=True,
):
    portfolio = Portfolio(
        user_id=user_id,
        name=name,
        is_active=is_active,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


def create_asset(
    db,
    name="Apple Inc.",
    symbol="AAPL",
    asset_type="STOCK",
    pricing_currency="USD",
    market="NASDAQ",
    is_market_backed=True,
    valuation_method="MARKET",
    unit="SHARE",
    is_active=True,
):
    asset = Asset(
        name=name,
        symbol=symbol,
        asset_type=asset_type,
        pricing_currency=pricing_currency,
        market=market,
        is_market_backed=is_market_backed,
        valuation_method=valuation_method,
        unit=unit,
        is_active=is_active,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def make_create_data(**overrides):
    data = {
        "portfolio_id": overrides.pop("portfolio_id", None),
        "source_account_id": overrides.pop("source_account_id", None),
        "destination_account_id": overrides.pop(
            "destination_account_id",
            None,
        ),
        "asset_id": overrides.pop("asset_id", None),
        "transaction_type": overrides.pop(
            "transaction_type",
            TransactionType.EXPENSE,
        ),
        "status": overrides.pop(
            "status",
            TransactionStatus.COMPLETED,
        ),
        "external_reference": overrides.pop(
            "external_reference",
            "EXT-001",
        ),
        "amount": overrides.pop(
            "amount",
            Decimal("100.00"),
        ),
        "currency": overrides.pop(
            "currency",
            "usd",
        ),
        "quantity": overrides.pop(
            "quantity",
            None,
        ),
        "unit": overrides.pop(
            "unit",
            None,
        ),
        "unit_price": overrides.pop(
            "unit_price",
            None,
        ),
        "merchant": overrides.pop(
            "merchant",
            "Test Merchant",
        ),
        "description": overrides.pop(
            "description",
            "Test transaction",
        ),
        "transaction_date": overrides.pop(
            "transaction_date",
            datetime.now(timezone.utc),
        ),
    }

    data.update(overrides)

    return TransactionCreate(**data)


def make_buy_data(
    portfolio_id,
    source_account_id,
    asset_id,
    **overrides,
):
    data = {
        "portfolio_id": portfolio_id,
        "source_account_id": source_account_id,
        "asset_id": asset_id,
        "transaction_type": TransactionType.BUY,
        "amount": Decimal("500.00"),
        "quantity": Decimal("5"),
        "unit": "SHARE",
        "unit_price": Decimal("100.00"),
    }

    data.update(overrides)

    return make_create_data(**data)


def make_sell_data(
    portfolio_id,
    destination_account_id,
    asset_id,
    **overrides,
):
    return make_create_data(
        portfolio_id=portfolio_id,
        destination_account_id=destination_account_id,
        asset_id=asset_id,
        transaction_type=TransactionType.SELL,
        amount=Decimal("500.00"),
        quantity=Decimal("5"),
        unit="SHARE",
        unit_price=Decimal("100.00"),
        **overrides,
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_completed_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        transaction_type=TransactionType.EXPENSE,
    )

    transaction = service.create_transaction(user.id, data)

    assert transaction.id is not None
    assert transaction.source_account_id == account.id
    assert transaction.transaction_type == TransactionType.EXPENSE.value
    assert transaction.status == TransactionStatus.COMPLETED.value
    assert transaction.amount == Decimal("100.00")
    assert transaction.currency == "USD"


def test_create_failed_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        status=TransactionStatus.FAILED,
    )

    transaction = service.create_transaction(user.id, data)

    assert transaction.status == TransactionStatus.FAILED.value


def test_create_cancelled_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        status=TransactionStatus.CANCELLED,
    )

    transaction = service.create_transaction(user.id, data)

    assert transaction.status == TransactionStatus.CANCELLED.value


def test_create_transaction_normalizes_currency(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        currency=" ngn ",
    )

    transaction = service.create_transaction(user.id, data)

    assert transaction.currency == "NGN"


@pytest.mark.parametrize(
    "transaction_type",
    [
        TransactionType.BUY,
        TransactionType.SELL,
        TransactionType.DEPOSIT,
        TransactionType.WITHDRAWAL,
        TransactionType.EXPENSE,
        TransactionType.TRANSFER,
        TransactionType.DIVIDEND,
        TransactionType.INTEREST,
        TransactionType.FEE,
    ],
)
def test_create_all_supported_transaction_types(
    db,
    transaction_type,
):
    user = create_user(db)
    source = create_account(
        db,
        user.id,
        name="Source",
    )
    destination = create_account(
        db,
        user.id,
        name="Destination",
    )
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    if transaction_type == TransactionType.BUY:
        data = make_buy_data(
            portfolio.id,
            source.id,
            asset.id,
        )

    elif transaction_type == TransactionType.SELL:
        data = make_sell_data(
            portfolio.id,
            destination.id,
            asset.id,
        )

    elif transaction_type == TransactionType.DEPOSIT:
        data = make_create_data(
            destination_account_id=destination.id,
            transaction_type=transaction_type,
        )

    elif transaction_type in {
        TransactionType.WITHDRAWAL,
        TransactionType.EXPENSE,
        TransactionType.FEE,
    }:
        data = make_create_data(
            source_account_id=source.id,
            transaction_type=transaction_type,
        )

    elif transaction_type == TransactionType.TRANSFER:
        data = make_create_data(
            source_account_id=source.id,
            destination_account_id=destination.id,
            transaction_type=transaction_type,
        )

    elif transaction_type == TransactionType.DIVIDEND:
        data = make_create_data(
            asset_id=asset.id,
            destination_account_id=destination.id,
            transaction_type=transaction_type,
        )

    elif transaction_type == TransactionType.INTEREST:
        data = make_create_data(
            destination_account_id=destination.id,
            transaction_type=transaction_type,
        )

    else:
        raise AssertionError(
            f"Unhandled transaction type: {transaction_type}"
        )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.transaction_type == transaction_type.value


def test_create_ownerless_transaction_is_rejected(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data()

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


# ---------------------------------------------------------------------------
# BUY / SELL
# ---------------------------------------------------------------------------


def test_buy_transaction_can_be_created(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    data = make_buy_data(
        portfolio.id,
        account.id,
        asset.id,
    )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.asset_id == asset.id
    assert transaction.quantity == Decimal("5")
    assert transaction.unit == "SHARE"
    assert transaction.unit_price == Decimal("100.00")


def test_sell_transaction_can_be_created(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    data = make_sell_data(
        portfolio.id,
        account.id,
        asset.id,
    )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.asset_id == asset.id
    assert transaction.quantity == Decimal("5")
    assert transaction.unit == "SHARE"
    assert transaction.unit_price == Decimal("100.00")


@pytest.mark.parametrize(
    "missing_field",
    [
        "asset_id",
        "quantity",
        "unit",
        "unit_price",
    ],
)

def test_buy_requires_complete_trade_fields(
    db,
    missing_field,
):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    values = {
        "portfolio_id": portfolio.id,
        "source_account_id": account.id,
        "asset_id": asset.id,
        "transaction_type": TransactionType.BUY,
        "amount": Decimal("500"),
        "quantity": Decimal("5"),
        "unit": "SHARE",
        "unit_price": Decimal("100"),
        "currency": "USD",
        "transaction_date": datetime.now(timezone.utc),
    }

    values[missing_field] = None

    with pytest.raises(PydanticValidationError):
        TransactionCreate(**values)


@pytest.mark.parametrize(
    "missing_field",
    [
        "asset_id",
        "quantity",
        "unit",
        "unit_price",
    ],
)

def test_sell_requires_complete_trade_fields(
    db,
    missing_field,
):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    values = {
        "portfolio_id": portfolio.id,
        "destination_account_id": account.id,
        "asset_id": asset.id,
        "transaction_type": TransactionType.SELL,
        "amount": Decimal("500"),
        "quantity": Decimal("5"),
        "unit": "SHARE",
        "unit_price": Decimal("100"),
        "currency": "USD",
        "transaction_date": datetime.now(timezone.utc),
    }

    values[missing_field] = None

    with pytest.raises(PydanticValidationError):
        TransactionCreate(**values)


@pytest.mark.parametrize(
    "quantity,unit",
    [
        (Decimal("5"), None),
        (None, "SHARE"),
    ],
)

def test_quantity_and_unit_must_be_supplied_together(
    quantity,
    unit,
):
    with pytest.raises(PydanticValidationError):
        TransactionCreate(
            source_account_id=1,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency="USD",
            quantity=quantity,
            unit=unit,
            transaction_date=datetime.now(timezone.utc),
        )


def test_unit_price_requires_quantity():
    with pytest.raises(PydanticValidationError):
        TransactionCreate(
            source_account_id=1,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("100"),
            currency="USD",
            unit_price=Decimal("10"),
            transaction_date=datetime.now(timezone.utc),
        )


def test_transfer_requires_both_accounts():
    with pytest.raises(PydanticValidationError):
        TransactionCreate(
            transaction_type=TransactionType.TRANSFER,
            amount=Decimal("100"),
            currency="USD",
            transaction_date=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Transaction semantic validation
# ---------------------------------------------------------------------------


def test_deposit_requires_destination_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.DEPOSIT,
        portfolio_id=None,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_withdrawal_requires_source_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.WITHDRAWAL,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_expense_requires_source_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.EXPENSE,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_transfer_requires_source_account():
    with pytest.raises(
        PydanticValidationError,
        match="TRANSFER transactions require both source and destination accounts",
    ):
        TransactionCreate(
            transaction_type=TransactionType.TRANSFER,
            destination_account_id=1,
            amount=Decimal("100.00"),
            currency="NGN",
            transaction_date=datetime.now(timezone.utc),
        )


def test_transfer_requires_destination_account():
    with pytest.raises(
        PydanticValidationError,
        match="TRANSFER transactions require both source and destination accounts",
    ):
        TransactionCreate(
            transaction_type=TransactionType.TRANSFER,
            source_account_id=1,
            amount=Decimal("100.00"),
            currency="NGN",
            transaction_date=datetime.now(timezone.utc),
        )


def test_transfer_cannot_use_same_account(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.TRANSFER,
        source_account_id=account.id,
        destination_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_dividend_requires_destination_account(db):
    user = create_user(db)
    asset = create_asset(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.DIVIDEND,
        asset_id=asset.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_dividend_requires_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.DIVIDEND,
        destination_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_interest_requires_destination_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.INTEREST,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_fee_requires_source_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        transaction_type=TransactionType.FEE,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_buy_requires_asset_at_service_boundary(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)

    service = TransactionService(db)

    data = TransactionCreate.model_construct(
        portfolio_id=portfolio.id,
        source_account_id=account.id,
        destination_account_id=None,
        asset_id=None,
        transaction_type=TransactionType.BUY,
        status=TransactionStatus.COMPLETED,
        external_reference="EXT-BUY-NO-ASSET",
        amount=Decimal("500.00"),
        currency="USD",
        quantity=Decimal("5"),
        unit="SHARE",
        unit_price=Decimal("100.00"),
        merchant="Test Merchant",
        description="Test transaction",
        transaction_date=datetime.now(timezone.utc),
    )

    with pytest.raises(
        ValidationError,
        match="asset_id is required for BUY and SELL transactions",
    ):
        service.create_transaction(user.id, data)


def test_sell_requires_asset_at_service_boundary(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)

    service = TransactionService(db)

    data = TransactionCreate.model_construct(
        portfolio_id=portfolio.id,
        source_account_id=None,
        destination_account_id=account.id,
        asset_id=None,
        transaction_type=TransactionType.SELL,
        status=TransactionStatus.COMPLETED,
        external_reference="EXT-SELL-NO-ASSET",
        amount=Decimal("500.00"),
        currency="USD",
        quantity=Decimal("5"),
        unit="SHARE",
        unit_price=Decimal("100.00"),
        merchant="Test Merchant",
        description="Test transaction",
        transaction_date=datetime.now(timezone.utc),
    )

    with pytest.raises(
        ValidationError,
        match="asset_id is required for BUY and SELL transactions",
    ):
        service.create_transaction(user.id, data)


# ---------------------------------------------------------------------------
# Resource ownership
# ---------------------------------------------------------------------------


def test_create_rejects_foreign_portfolio(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    attacker = create_user(
        db,
        "attacker@example.com",
    )

    portfolio = create_portfolio(
        db,
        owner.id,
    )
    account = create_account(
        db,
        attacker.id,
    )

    service = TransactionService(db)

    data = make_create_data(
        portfolio_id=portfolio.id,
        source_account_id=account.id,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_transaction(
            attacker.id,
            data,
        )


def test_create_rejects_foreign_source_account(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    attacker = create_user(
        db,
        "attacker@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_transaction(
            attacker.id,
            data,
        )


def test_create_rejects_foreign_destination_account(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    attacker = create_user(
        db,
        "attacker@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    data = make_create_data(
        destination_account_id=account.id,
        transaction_type=TransactionType.DEPOSIT,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_transaction(
            attacker.id,
            data,
        )


def test_create_rejects_nonexistent_portfolio(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        portfolio_id=999999,
        source_account_id=account.id,
    )

    with pytest.raises(NotFoundError):
        service.create_transaction(
            user.id,
            data,
        )


def test_create_rejects_nonexistent_account(db):
    user = create_user(db)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=999999,
    )

    with pytest.raises(NotFoundError):
        service.create_transaction(
            user.id,
            data,
        )


def test_create_rejects_nonexistent_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=999999,
    )

    with pytest.raises(NotFoundError):
        service.create_transaction(
            user.id,
            data,
        )


def test_asset_is_global_and_does_not_require_user_ownership(db):
    user = create_user(db)
    account = create_account(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=asset.id,
    )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.asset_id == asset.id


# ---------------------------------------------------------------------------
# Resource activity
# ---------------------------------------------------------------------------


def test_create_rejects_inactive_account(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_create_rejects_inactive_destination_account(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        destination_account_id=account.id,
        transaction_type=TransactionType.DEPOSIT,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_create_rejects_inactive_portfolio(db):
    user = create_user(db)
    account = create_account(
        db,
        user.id,
    )

    portfolio = create_portfolio(
        db,
        user.id,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        portfolio_id=portfolio.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_create_rejects_inactive_asset(db):
    user = create_user(db)
    account = create_account(
        db,
        user.id,
    )

    asset = create_asset(
        db,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=asset.id,
    )

    with pytest.raises(ValidationError):
        service.create_transaction(
            user.id,
            data,
        )


def test_failed_transaction_can_reference_inactive_account(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        status=TransactionStatus.FAILED,
    )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.source_account_id == account.id
    assert transaction.status == TransactionStatus.FAILED.value


def test_cancelled_transaction_can_reference_inactive_portfolio(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
    )

    portfolio = create_portfolio(
        db,
        user.id,
        is_active=False,
    )

    service = TransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        portfolio_id=portfolio.id,
        status=TransactionStatus.CANCELLED,
    )

    transaction = service.create_transaction(
        user.id,
        data,
    )

    assert transaction.portfolio_id == portfolio.id
    assert transaction.status == TransactionStatus.CANCELLED.value


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_get_transaction_returns_owned_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    result = service.get_transaction(
        user.id,
        transaction.id,
    )

    assert result is not None
    assert result.id == transaction.id


def test_get_transaction_returns_none_for_foreign_transaction(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other_user = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    transaction = service.create_transaction(
        owner.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    result = service.get_transaction(
        other_user.id,
        transaction.id,
    )

    assert result is None


def test_get_transaction_returns_none_for_missing_transaction(db):
    user = create_user(db)

    service = TransactionService(db)

    result = service.get_transaction(
        user.id,
        999999,
    )

    assert result is None


def test_require_transaction_raises_for_missing_transaction(db):
    user = create_user(db)

    service = TransactionService(db)

    with pytest.raises(NotFoundError):
        service.require_transaction(
            user.id,
            999999,
        )


def test_require_transaction_rejects_foreign_transaction(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other_user = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    transaction = service.create_transaction(
        owner.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    with pytest.raises(NotFoundError):
        service.require_transaction(
            other_user.id,
            transaction.id,
        )


# ---------------------------------------------------------------------------
# Listing / filtering
# ---------------------------------------------------------------------------


def test_list_transactions_is_user_scoped(db):
    user_one = create_user(
        db,
        "one@example.com",
    )
    user_two = create_user(
        db,
        "two@example.com",
    )

    account_one = create_account(
        db,
        user_one.id,
    )
    account_two = create_account(
        db,
        user_two.id,
    )

    service = TransactionService(db)

    transaction_one = service.create_transaction(
        user_one.id,
        make_create_data(
            source_account_id=account_one.id,
            external_reference="ONE",
        ),
    )

    service.create_transaction(
        user_two.id,
        make_create_data(
            source_account_id=account_two.id,
            external_reference="TWO",
        ),
    )

    results = service.list_transactions(
        user_one.id,
    )

    assert len(results) == 1
    assert results[0].id == transaction_one.id


def test_list_transactions_filters_by_portfolio(db):
    user = create_user(db)
    account = create_account(db, user.id)

    portfolio_one = create_portfolio(
        db,
        user.id,
        name="Portfolio One",
    )
    portfolio_two = create_portfolio(
        db,
        user.id,
        name="Portfolio Two",
    )

    service = TransactionService(db)

    first = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            portfolio_id=portfolio_one.id,
            external_reference="ONE",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            portfolio_id=portfolio_two.id,
            external_reference="TWO",
        ),
    )

    results = service.list_transactions(
        user.id,
        portfolio_id=portfolio_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_transactions_filters_by_account(db):
    user = create_user(db)

    account_one = create_account(
        db,
        user.id,
        name="Account One",
    )
    account_two = create_account(
        db,
        user.id,
        name="Account Two",
    )

    service = TransactionService(db)

    first = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account_one.id,
            external_reference="ONE",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account_two.id,
            external_reference="TWO",
        ),
    )

    results = service.list_transactions(
        user.id,
        account_id=account_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_transactions_filters_destination_account(db):
    user = create_user(db)

    destination_one = create_account(
        db,
        user.id,
        name="Destination One",
    )
    destination_two = create_account(
        db,
        user.id,
        name="Destination Two",
    )

    service = TransactionService(db)

    first = service.create_transaction(
        user.id,
        make_create_data(
            destination_account_id=destination_one.id,
            transaction_type=TransactionType.DEPOSIT,
            external_reference="ONE",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            destination_account_id=destination_two.id,
            transaction_type=TransactionType.DEPOSIT,
            external_reference="TWO",
        ),
    )

    results = service.list_transactions(
        user.id,
        account_id=destination_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_transactions_filters_by_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)

    asset_one = create_asset(
        db,
        name="Asset One",
        symbol="AAA",
    )
    asset_two = create_asset(
        db,
        name="Asset Two",
        symbol="BBB",
    )

    service = TransactionService(db)

    first = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            asset_id=asset_one.id,
            external_reference="ONE",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            asset_id=asset_two.id,
            external_reference="TWO",
        ),
    )

    results = service.list_transactions(
        user.id,
        asset_id=asset_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_transactions_filters_by_type(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    expense = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            transaction_type=TransactionType.EXPENSE,
            external_reference="EXPENSE",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            transaction_type=TransactionType.FEE,
            external_reference="FEE",
        ),
    )

    results = service.list_transactions(
        user.id,
        transaction_type=TransactionType.EXPENSE,
    )

    assert [item.id for item in results] == [expense.id]


def test_list_transactions_filters_by_status(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    failed = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
            external_reference="FAILED",
        ),
    )

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.COMPLETED,
            external_reference="COMPLETED",
        ),
    )

    results = service.list_transactions(
        user.id,
        status=TransactionStatus.FAILED,
    )

    assert [item.id for item in results] == [failed.id]


def test_list_transactions_orders_newest_first(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    older = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="OLDER",
            transaction_date=datetime(
                2026,
                1,
                1,
                tzinfo=timezone.utc,
            ),
        ),
    )

    newer = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="NEWER",
            transaction_date=datetime(
                2026,
                2,
                1,
                tzinfo=timezone.utc,
            ),
        ),
    )

    results = service.list_transactions(
        user.id,
    )

    assert [item.id for item in results] == [
        newer.id,
        older.id,
    ]


def test_list_transactions_uses_id_as_tie_breaker(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction_date = datetime(
        2026,
        3,
        1,
        tzinfo=timezone.utc,
    )

    first = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="FIRST",
            transaction_date=transaction_date,
        ),
    )

    second = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="SECOND",
            transaction_date=transaction_date,
        ),
    )

    results = service.list_transactions(
        user.id,
    )

    assert [item.id for item in results] == [
        second.id,
        first.id,
    ]


def test_list_transactions_rejects_foreign_portfolio_filter(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other = create_user(
        db,
        "other@example.com",
    )

    portfolio = create_portfolio(
        db,
        owner.id,
    )

    service = TransactionService(db)

    with pytest.raises(NotFoundError):
        service.list_transactions(
            other.id,
            portfolio_id=portfolio.id,
        )


def test_list_transactions_rejects_foreign_account_filter(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    with pytest.raises(NotFoundError):
        service.list_transactions(
            other.id,
            account_id=account.id,
        )


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


def test_completed_transaction_is_immutable(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    update = TransactionUpdate(
        amount=Decimal("200"),
    )

    with pytest.raises(ConflictError):
        service.update_transaction(
            user.id,
            transaction.id,
            update,
        )


def test_completed_transaction_cannot_change_description(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    update = TransactionUpdate(
        description="Changed",
    )

    with pytest.raises(ConflictError):
        service.update_transaction(
            user.id,
            transaction.id,
            update,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", Decimal("200")),
        ("currency", "EUR"),
        ("quantity", Decimal("10")),
        ("unit", "COIN"),
        ("unit_price", Decimal("20")),
        ("portfolio_id", 999),
        ("source_account_id", 999),
        ("destination_account_id", 999),
        ("asset_id", 999),
        ("transaction_type", TransactionType.FEE),
        ("status", TransactionStatus.COMPLETED),
        ("transaction_date", datetime.now(timezone.utc)),
    ],
)
def test_failed_transaction_cannot_change_financial_fields(
    db,
    field,
    value,
):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    update = TransactionUpdate(
        **{field: value},
    )

    with pytest.raises(ConflictError):
        service.update_transaction(
            user.id,
            transaction.id,
            update,
        )


def test_failed_transaction_can_update_external_reference(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    update = TransactionUpdate(
        external_reference="CORRECTED-REF",
    )

    updated = service.update_transaction(
        user.id,
        transaction.id,
        update,
    )

    assert updated.external_reference == "CORRECTED-REF"


def test_failed_transaction_can_update_merchant(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    updated = service.update_transaction(
        user.id,
        transaction.id,
        TransactionUpdate(
            merchant="Updated Merchant",
        ),
    )

    assert updated.merchant == "Updated Merchant"


def test_failed_transaction_can_update_description(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    updated = service.update_transaction(
        user.id,
        transaction.id,
        TransactionUpdate(
            description="Updated description",
        ),
    )

    assert updated.description == "Updated description"


def test_cancelled_transaction_can_update_metadata(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.CANCELLED,
        ),
    )

    update = TransactionUpdate(
        merchant="Corrected Merchant",
        description="Corrected description",
    )

    updated = service.update_transaction(
        user.id,
        transaction.id,
        update,
    )

    assert updated.merchant == "Corrected Merchant"
    assert updated.description == "Corrected description"


def test_update_does_not_allow_foreign_transaction(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    transaction = service.create_transaction(
        owner.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    update = TransactionUpdate(
        description="Unauthorized",
    )

    with pytest.raises(NotFoundError):
        service.update_transaction(
            other.id,
            transaction.id,
            update,
        )


def test_empty_historical_update_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    updated = service.update_transaction(
        user.id,
        transaction.id,
        TransactionUpdate(),
    )

    assert updated.id == transaction.id
    assert updated.status == TransactionStatus.FAILED.value


def test_update_rejects_unknown_fields():
    with pytest.raises(PydanticValidationError):
        TransactionUpdate(
            unknown_field="not allowed",
        )


# ---------------------------------------------------------------------------
# Cancellation / failure
# ---------------------------------------------------------------------------


def test_cancel_completed_transaction_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    with pytest.raises(ConflictError):
        service.cancel_transaction(
            user.id,
            transaction.id,
        )


def test_cancel_failed_transaction_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    with pytest.raises(ConflictError):
        service.cancel_transaction(
            user.id,
            transaction.id,
        )


def test_cancel_already_cancelled_transaction_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.CANCELLED,
        ),
    )

    result = service.cancel_transaction(
        user.id,
        transaction.id,
    )

    assert result.id == transaction.id
    assert result.status == TransactionStatus.CANCELLED.value


def test_mark_failed_completed_transaction_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    with pytest.raises(ConflictError):
        service.mark_failed(
            user.id,
            transaction.id,
        )


def test_mark_failed_cancelled_transaction_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.CANCELLED,
        ),
    )

    with pytest.raises(ConflictError):
        service.mark_failed(
            user.id,
            transaction.id,
        )


def test_mark_failed_already_failed_transaction_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            status=TransactionStatus.FAILED,
        ),
    )

    result = service.mark_failed(
        user.id,
        transaction.id,
    )

    assert result.id == transaction.id
    assert result.status == TransactionStatus.FAILED.value


def test_cancel_requires_ownership(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    transaction = service.create_transaction(
        owner.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    with pytest.raises(NotFoundError):
        service.cancel_transaction(
            other.id,
            transaction.id,
        )


def test_mark_failed_requires_ownership(db):
    owner = create_user(
        db,
        "owner@example.com",
    )
    other = create_user(
        db,
        "other@example.com",
    )

    account = create_account(
        db,
        owner.id,
    )

    service = TransactionService(db)

    transaction = service.create_transaction(
        owner.id,
        make_create_data(
            source_account_id=account.id,
        ),
    )

    with pytest.raises(NotFoundError):
        service.mark_failed(
            other.id,
            transaction.id,
        )


# ---------------------------------------------------------------------------
# Precision / persistence
# ---------------------------------------------------------------------------


def test_transaction_preserves_decimal_precision(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    amount = Decimal("123456789012.12345678")

    transaction = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            amount=amount,
        ),
    )

    assert transaction.amount == amount


def test_transaction_preserves_quantity_precision(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    quantity = Decimal("123456789012.12345678")

    transaction = service.create_transaction(
        user.id,
        make_buy_data(
            portfolio.id,
            account.id,
            asset.id,
            quantity=quantity,
            unit_price=Decimal("1.00000000"),
            amount=Decimal("123456789012.12345678"),
        ),
    )

    assert transaction.quantity == quantity


def test_transaction_preserves_unit_price_precision(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id)
    asset = create_asset(db)

    service = TransactionService(db)

    unit_price = Decimal("123456789012.12345678")

    transaction = service.create_transaction(
        user.id,
        make_buy_data(
            portfolio.id,
            account.id,
            asset.id,
            quantity=Decimal("1"),
            unit_price=unit_price,
            amount=unit_price,
        ),
    )

    assert transaction.unit_price == unit_price


def test_transaction_external_reference_is_not_globally_unique(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = TransactionService(db)

    first = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="SAME-REF",
        ),
    )

    second = service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            external_reference="SAME-REF",
        ),
    )

    assert first.id != second.id
    assert first.external_reference == second.external_reference


# ---------------------------------------------------------------------------
# Transaction persistence / financial-state boundary
# ---------------------------------------------------------------------------


def test_creating_transaction_does_not_modify_account_balance(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
    )

    original_balance = account.balance

    service = TransactionService(db)

    service.create_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            transaction_type=TransactionType.EXPENSE,
        ),
    )

    db.refresh(account)

    assert account.balance == original_balance


def test_creating_buy_transaction_does_not_create_holding(db):
    user = create_user(db)
    account = create_account(
        db,
        user.id,
    )
    portfolio = create_portfolio(
        db,
        user.id,
    )
    asset = create_asset(db)

    service = TransactionService(db)

    transaction = service.create_transaction(
        user.id,
        make_buy_data(
            portfolio.id,
            account.id,
            asset.id,
        ),
    )

    assert transaction.id is not None

    portfolio_holdings = list(portfolio.holdings)

    assert portfolio_holdings == []
