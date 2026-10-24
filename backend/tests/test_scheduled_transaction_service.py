from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.exceptions.common import ConflictError, NotFoundError, ValidationError
from app.models.account import Account
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.scheduled_transaction import (
    RecurrenceType,
    ScheduledTransaction,
    ScheduledTransactionExecutionMode,
    ScheduledTransactionStatus,
    ScheduledTransactionType,
)
from app.schemas.scheduled_transaction import (
    ScheduledTransactionCreate,
    ScheduledTransactionUpdate,
)
from app.services.scheduled_transaction_service import ScheduledTransactionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_user(db, email="user@example.com"):
    from app.models.user import User

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
        "scheduled_type": overrides.pop(
            "scheduled_type",
            ScheduledTransactionType.EXPENSE,
        ),
        "execution_mode": overrides.pop(
            "execution_mode",
            ScheduledTransactionExecutionMode.AMOUNT,
        ),
        "status": overrides.pop(
            "status",
            ScheduledTransactionStatus.SCHEDULED,
        ),
        "is_recurring": overrides.pop(
            "is_recurring",
            False,
        ),
        "recurrence": overrides.pop(
            "recurrence",
            None,
        ),
        "recurrence_end_date": overrides.pop(
            "recurrence_end_date",
            None,
        ),
        "recurrence_count": overrides.pop(
            "recurrence_count",
            None,
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
        "external_reference": overrides.pop(
            "external_reference",
            "SCHED-001",
        ),
        "description": overrides.pop(
            "description",
            "Test scheduled transaction",
        ),
        "scheduled_date": overrides.pop(
            "scheduled_date",
            datetime(
                2026,
                9,
                10,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        ),
    }

    data.update(overrides)

    return ScheduledTransactionCreate(**data)


def create_schedule(
    db,
    user_id,
    *,
    scheduled_type=ScheduledTransactionType.EXPENSE,
    execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
    status=ScheduledTransactionStatus.SCHEDULED,
    is_recurring=False,
    recurrence=None,
    recurrence_end_date=None,
    recurrence_count=None,
    execution_count=0,
    source_account_id=None,
    destination_account_id=None,
    portfolio_id=None,
    asset_id=None,
    amount=Decimal("100.00"),
    currency="USD",
    quantity=None,
    unit=None,
    unit_price=None,
    scheduled_date=None,
):
    schedule = ScheduledTransaction(
        user_id=user_id,
        portfolio_id=portfolio_id,
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        asset_id=asset_id,
        scheduled_type=(
            scheduled_type.value
            if isinstance(scheduled_type, ScheduledTransactionType)
            else scheduled_type
        ),
        execution_mode=(
            execution_mode.value
            if isinstance(
                execution_mode,
                ScheduledTransactionExecutionMode,
            )
            else execution_mode
        ),
        status=(
            status.value
            if isinstance(status, ScheduledTransactionStatus)
            else status
        ),
        is_recurring=is_recurring,
        recurrence=(
            recurrence.value
            if isinstance(recurrence, RecurrenceType)
            else recurrence
        ),
        recurrence_end_date=recurrence_end_date,
        recurrence_count=recurrence_count,
        execution_count=execution_count,
        amount=amount,
        currency=currency,
        quantity=quantity,
        unit=unit,
        unit_price=unit_price,
        merchant="Test Merchant",
        external_reference="SCHED-001",
        description="Test scheduled transaction",
        scheduled_date=scheduled_date
        or datetime(
            2026,
            9,
            10,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return schedule


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_scheduled_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        scheduled_type=ScheduledTransactionType.EXPENSE,
    )

    schedule = service.create_scheduled_transaction(
        user.id,
        data,
    )

    assert schedule.id is not None
    assert schedule.user_id == user.id
    assert schedule.source_account_id == account.id
    assert schedule.scheduled_type == ScheduledTransactionType.EXPENSE.value
    assert schedule.status == ScheduledTransactionStatus.SCHEDULED.value
    assert schedule.execution_count == 0


def test_create_scheduled_transaction_normalizes_currency(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        currency=" ngn ",
    )

    schedule = service.create_scheduled_transaction(
        user.id,
        data,
    )

    assert schedule.currency == "NGN"


def test_create_ownerless_schedule_is_rejected(db):
    user = create_user(db)

    service = ScheduledTransactionService(db)

    data = make_create_data()

    with pytest.raises(ValidationError):
        service.create_scheduled_transaction(
            user.id,
            data,
        )


@pytest.mark.parametrize(
    "scheduled_type",
    [
        ScheduledTransactionType.BUY,
        ScheduledTransactionType.SELL,
        ScheduledTransactionType.DEPOSIT,
        ScheduledTransactionType.WITHDRAWAL,
        ScheduledTransactionType.EXPENSE,
        ScheduledTransactionType.TRANSFER,
        ScheduledTransactionType.DIVIDEND,
        ScheduledTransactionType.INTEREST,
        ScheduledTransactionType.FEE,
    ],
)
def test_create_supported_scheduled_transaction_types(
    db,
    scheduled_type,
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

    portfolio = create_portfolio(
        db,
        user.id,
    )

    asset = create_asset(db)

    service = ScheduledTransactionService(db)

    if scheduled_type == ScheduledTransactionType.BUY:
        data = make_create_data(
            scheduled_type=scheduled_type,
            execution_mode=ScheduledTransactionExecutionMode.BOTH,
            source_account_id=source.id,
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("5"),
            unit="SHARE",
            unit_price=Decimal("100"),
        )

    elif scheduled_type == ScheduledTransactionType.SELL:
        data = make_create_data(
            scheduled_type=scheduled_type,
            execution_mode=ScheduledTransactionExecutionMode.BOTH,
            destination_account_id=destination.id,
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("5"),
            unit="SHARE",
            unit_price=Decimal("100"),
        )

    elif scheduled_type == ScheduledTransactionType.DEPOSIT:
        data = make_create_data(
            scheduled_type=scheduled_type,
            destination_account_id=destination.id,
        )

    elif scheduled_type in {
        ScheduledTransactionType.WITHDRAWAL,
        ScheduledTransactionType.EXPENSE,
        ScheduledTransactionType.FEE,
    }:
        data = make_create_data(
            scheduled_type=scheduled_type,
            source_account_id=source.id,
        )

    elif scheduled_type == ScheduledTransactionType.TRANSFER:
        data = make_create_data(
            scheduled_type=scheduled_type,
            source_account_id=source.id,
            destination_account_id=destination.id,
        )

    elif scheduled_type == ScheduledTransactionType.DIVIDEND:
        data = make_create_data(
            scheduled_type=scheduled_type,
            asset_id=asset.id,
            destination_account_id=destination.id,
        )

    elif scheduled_type == ScheduledTransactionType.INTEREST:
        data = make_create_data(
            scheduled_type=scheduled_type,
            destination_account_id=destination.id,
        )

    else:
        raise AssertionError(
            f"Unhandled scheduled transaction type: {scheduled_type}"
        )

    schedule = service.create_scheduled_transaction(
        user.id,
        data,
    )

    assert schedule.scheduled_type == scheduled_type.value


# ---------------------------------------------------------------------------
# Execution mode / structural validation at schema boundary
# ---------------------------------------------------------------------------


def test_amount_execution_mode_requires_amount():
    with pytest.raises(PydanticValidationError):
        make_create_data(
            execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
            amount=None,
        )


def test_quantity_execution_mode_requires_quantity():
    with pytest.raises(PydanticValidationError):
        make_create_data(
            execution_mode=ScheduledTransactionExecutionMode.QUANTITY,
            amount=None,
            quantity=None,
            unit=None,
            unit_price=None,
        )


def test_both_execution_mode_requires_amount_and_quantity():
    with pytest.raises(PydanticValidationError):
        make_create_data(
            scheduled_type=ScheduledTransactionType.BUY,
            execution_mode=ScheduledTransactionExecutionMode.BOTH,
            amount=None,
            quantity=Decimal("5"),
            unit="SHARE",
            unit_price=Decimal("100"),
            portfolio_id=1,
            source_account_id=1,
            asset_id=1,
        )


def test_update_rejects_unknown_fields():
    with pytest.raises(PydanticValidationError):
        ScheduledTransactionUpdate(
            unknown_field="not allowed",
        )


# ---------------------------------------------------------------------------
# Ownership / resource validation
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

    service = ScheduledTransactionService(db)

    data = make_create_data(
        portfolio_id=portfolio.id,
        source_account_id=account.id,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_scheduled_transaction(
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

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_scheduled_transaction(
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

    service = ScheduledTransactionService(db)

    data = make_create_data(
        scheduled_type=ScheduledTransactionType.DEPOSIT,
        destination_account_id=account.id,
    )

    with pytest.raises((NotFoundError, ValidationError)):
        service.create_scheduled_transaction(
            attacker.id,
            data,
        )


def test_create_rejects_nonexistent_account(db):
    user = create_user(db)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=999999,
    )

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            data,
        )


def test_create_rejects_nonexistent_portfolio(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        portfolio_id=999999,
    )

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            data,
        )


def test_create_rejects_nonexistent_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=999999,
    )

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            data,
        )


def test_create_rejects_inactive_account(db):
    user = create_user(db)

    account = create_account(
        db,
        user.id,
        is_active=False,
    )

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        service.create_scheduled_transaction(
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

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        portfolio_id=portfolio.id,
    )

    with pytest.raises(ValidationError):
        service.create_scheduled_transaction(
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

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=asset.id,
    )

    with pytest.raises(ValidationError):
        service.create_scheduled_transaction(
            user.id,
            data,
        )


def test_asset_is_global_and_does_not_require_user_ownership(db):
    user = create_user(db)
    account = create_account(db, user.id)
    asset = create_asset(db)

    service = ScheduledTransactionService(db)

    data = make_create_data(
        source_account_id=account.id,
        asset_id=asset.id,
    )

    schedule = service.create_scheduled_transaction(
        user.id,
        data,
    )

    assert schedule.asset_id == asset.id


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_get_scheduled_transaction_returns_owned_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    result = service.get_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result is not None
    assert result.id == schedule.id


def test_get_scheduled_transaction_returns_none_for_wrong_user(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    result = service.get_scheduled_transaction(
        other.id,
        schedule.id,
    )

    assert result is None


def test_require_scheduled_transaction_returns_owned_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    result = service.require_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.id == schedule.id


def test_require_scheduled_transaction_rejects_wrong_user(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.require_scheduled_transaction(
            other.id,
            schedule.id,
        )


def test_require_scheduled_transaction_rejects_missing_schedule(db):
    user = create_user(db)

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.require_scheduled_transaction(
            user.id,
            999999,
        )


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_list_scheduled_transactions_is_user_scoped(db):
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

    first = create_schedule(
        db,
        user_one.id,
        source_account_id=account_one.id,
    )

    create_schedule(
        db,
        user_two.id,
        source_account_id=account_two.id,
    )

    service = ScheduledTransactionService(db)

    results = service.list_scheduled_transactions(
        user_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_scheduled_transactions_can_filter_by_status(db):
    user = create_user(db)
    account = create_account(db, user.id)

    scheduled = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.CANCELLED,
    )

    service = ScheduledTransactionService(db)

    results = service.list_scheduled_transactions(
        user.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    assert [item.id for item in results] == [scheduled.id]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_scheduled_transaction_changes_allowed_fields(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    updated = service.update_scheduled_transaction(
        user.id,
        schedule.id,
        ScheduledTransactionUpdate(
            merchant="Updated Merchant",
            description="Updated description",
        ),
    )

    assert updated.merchant == "Updated Merchant"
    assert updated.description == "Updated description"


def test_update_scheduled_transaction_rejects_foreign_schedule(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.update_scheduled_transaction(
            other.id,
            schedule.id,
            ScheduledTransactionUpdate(
                description="Unauthorized",
            ),
        )


def test_update_processing_schedule_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.update_scheduled_transaction(
            user.id,
            schedule.id,
            ScheduledTransactionUpdate(
                description="Cannot update",
            ),
        )


def test_update_completed_schedule_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.COMPLETED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.update_scheduled_transaction(
            user.id,
            schedule.id,
            ScheduledTransactionUpdate(
                description="Cannot update",
            ),
        )


def test_update_cancelled_schedule_is_rejected(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.CANCELLED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.update_scheduled_transaction(
            user.id,
            schedule.id,
            ScheduledTransactionUpdate(
                description="Cannot update",
            ),
        )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancel_scheduled_transaction_changes_status(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    result = service.cancel_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.CANCELLED.value


def test_cancel_scheduled_transaction_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.CANCELLED,
    )

    service = ScheduledTransactionService(db)

    result = service.cancel_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.id == schedule.id
    assert result.status == ScheduledTransactionStatus.CANCELLED.value


def test_cancel_cannot_cancel_processing_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.cancel_scheduled_transaction(
            user.id,
            schedule.id,
        )


def test_cancel_cannot_cancel_completed_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.COMPLETED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.cancel_scheduled_transaction(
            user.id,
            schedule.id,
        )


def test_wrong_user_cannot_cancel_schedule(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.cancel_scheduled_transaction(
            other.id,
            schedule.id,
        )


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


def test_pause_recurring_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
    )

    service = ScheduledTransactionService(db)

    result = service.pause_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PAUSED.value


def test_pause_non_recurring_schedule_fails(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=False,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.pause_scheduled_transaction(
            user.id,
            schedule.id,
        )


def test_pause_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        status=ScheduledTransactionStatus.PAUSED,
    )

    service = ScheduledTransactionService(db)

    result = service.pause_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PAUSED.value


def test_resume_paused_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        status=ScheduledTransactionStatus.PAUSED,
    )

    service = ScheduledTransactionService(db)

    result = service.resume_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value


def test_resume_scheduled_schedule_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    service = ScheduledTransactionService(db)

    result = service.resume_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value


def test_wrong_user_cannot_pause_schedule(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.pause_scheduled_transaction(
            other.id,
            schedule.id,
        )


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def test_mark_processing_moves_scheduled_to_processing(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_processing(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PROCESSING.value
    assert result.last_attempt_at is not None
    assert result.execution_error is None


def test_mark_processing_can_retry_failed_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.FAILED,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_processing(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PROCESSING.value
    assert result.execution_error is None


def test_mark_processing_rejects_completed_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.COMPLETED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.mark_processing(
            user.id,
            schedule.id,
        )


def test_mark_processing_rejects_cancelled_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.CANCELLED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.mark_processing(
            user.id,
            schedule.id,
        )


def test_mark_failed_moves_processing_to_failed(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_failed(
        user.id,
        schedule.id,
        "Execution failed.",
    )

    assert result.status == ScheduledTransactionStatus.FAILED.value
    assert result.execution_error == "Execution failed."
    assert result.last_attempt_at is not None


def test_mark_failed_requires_error_message(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ValidationError):
        service.mark_failed(
            user.id,
            schedule.id,
            "   ",
        )


def test_mark_failed_requires_processing_state(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.mark_failed(
            user.id,
            schedule.id,
            "Execution failed.",
        )


def test_wrong_user_cannot_process_schedule(db):
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

    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.mark_processing(
            other.id,
            schedule.id,
        )


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def test_mark_completed_non_recurring_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=False,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value
    assert result.execution_count == 1
    assert result.executed_at is not None
    assert result.execution_error is None


def test_mark_completed_requires_processing_state(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.mark_completed(
            user.id,
            schedule.id,
        )


def test_mark_completed_increments_execution_count(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        execution_count=2,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.execution_count == 3


def test_mark_completed_recurring_schedule_returns_to_scheduled(db):
    user = create_user(db)
    account = create_account(db, user.id)

    original_date = datetime(
        2026,
        9,
        10,
        10,
        0,
        tzinfo=timezone.utc,
    )

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_count=3,
        execution_count=0,
        scheduled_date=original_date,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value
    assert result.execution_count == 1
    assert result.scheduled_date == datetime(
        2026,
        10,
        10,
        10,
        0,
        tzinfo=timezone.utc,
    )


def test_mark_completed_recurring_schedule_finishes_at_recurrence_count(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_count=1,
        execution_count=0,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value
    assert result.execution_count == 1


def test_mark_completed_recurring_schedule_respects_end_date(db):
    user = create_user(db)
    account = create_account(db, user.id)

    original_date = datetime(
        2026,
        12,
        10,
        10,
        0,
        tzinfo=timezone.utc,
    )

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_end_date=datetime(
            2026,
            12,
            15,
            tzinfo=timezone.utc,
        ).date(),
        scheduled_date=original_date,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value
    assert result.execution_count == 1


# ---------------------------------------------------------------------------
# Recurrence calculations
# ---------------------------------------------------------------------------


def test_monthly_recurrence_clamps_end_of_month(db):
    user = create_user(db)
    account = create_account(db, user.id)

    original_date = datetime(
        2026,
        1,
        31,
        10,
        0,
        tzinfo=timezone.utc,
    )

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_count=3,
        scheduled_date=original_date,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value
    assert result.scheduled_date == datetime(
        2026,
        2,
        28,
        10,
        0,
        tzinfo=timezone.utc,
    )


def test_yearly_recurrence_handles_february_29(db):
    user = create_user(db)
    account = create_account(db, user.id)

    original_date = datetime(
        2028,
        2,
        29,
        10,
        0,
        tzinfo=timezone.utc,
    )

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.YEARLY,
        recurrence_count=3,
        scheduled_date=original_date,
    )

    service = ScheduledTransactionService(db)

    result = service.mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value
    assert result.scheduled_date == datetime(
        2029,
        2,
        28,
        10,
        0,
        tzinfo=timezone.utc,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_status_changes_are_persisted(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    service = ScheduledTransactionService(db)

    service.mark_processing(
        user.id,
        schedule.id,
    )

    db.expire_all()

    refreshed = service.require_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert refreshed.status == ScheduledTransactionStatus.PROCESSING.value


def test_failed_state_is_persisted(db):
    user = create_user(db)
    account = create_account(db, user.id)

    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    service = ScheduledTransactionService(db)

    service.mark_failed(
        user.id,
        schedule.id,
        "Provider unavailable.",
    )

    db.expire_all()

    refreshed = service.require_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert refreshed.status == ScheduledTransactionStatus.FAILED.value
    assert refreshed.execution_error == "Provider unavailable."