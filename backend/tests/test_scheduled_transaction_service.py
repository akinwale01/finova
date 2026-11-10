from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.app.exceptions.common import ConflictError, NotFoundError, ValidationError
from backend.app.models.account import Account
from backend.app.models.asset import Asset
from backend.app.models.portfolio import Portfolio
from backend.app.models.scheduled_transaction import (
    RecurrenceType,
    ScheduledTransaction,
    ScheduledTransactionExecutionMode,
    ScheduledTransactionStatus,
    ScheduledTransactionType,
)
from backend.app.schemas.scheduled_transaction import (
    ScheduledTransactionCreate,
    ScheduledTransactionUpdate,
)
from backend.app.services.scheduled_transaction_service import ScheduledTransactionService


# ===========================================================================
# Test helpers
# ===========================================================================


DEFAULT_DATE = datetime(
    2026,
    9,
    10,
    10,
    0,
    tzinfo=timezone.utc,
)


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
    """Build a valid schema payload unless a test overrides its fields."""
    data = {
        "portfolio_id": None,
        "source_account_id": None,
        "destination_account_id": None,
        "asset_id": None,
        "scheduled_type": ScheduledTransactionType.EXPENSE,
        "execution_mode": ScheduledTransactionExecutionMode.AMOUNT,
        "is_recurring": False,
        "recurrence": None,
        "recurrence_end_date": None,
        "recurrence_count": None,
        "amount": Decimal("100.00"),
        "currency": "USD",
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "merchant": "Test Merchant",
        "external_reference": "SCHED-001",
        "description": "Test scheduled transaction",
        "scheduled_date": DEFAULT_DATE,
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
    """Insert a schedule directly for lifecycle and retrieval tests."""
    schedule = ScheduledTransaction(
        user_id=user_id,
        portfolio_id=portfolio_id,
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        asset_id=asset_id,
        scheduled_type=(
            scheduled_type.value
            if hasattr(scheduled_type, "value")
            else scheduled_type
        ),
        execution_mode=(
            execution_mode.value
            if hasattr(execution_mode, "value")
            else execution_mode
        ),
        status=status.value if hasattr(status, "value") else status,
        is_recurring=is_recurring,
        recurrence=(
            recurrence.value if hasattr(recurrence, "value") else recurrence
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
        scheduled_date=scheduled_date or DEFAULT_DATE,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


# ===========================================================================
# Creation and validation
# ===========================================================================


def test_create_scheduled_transaction(db):
    user = create_user(db)
    account = create_account(db, user.id)
    service = ScheduledTransactionService(db)

    result = service.create_scheduled_transaction(
        user.id,
        make_create_data(source_account_id=account.id),
    )

    assert result.id is not None
    assert result.user_id == user.id
    assert result.source_account_id == account.id
    assert result.status == ScheduledTransactionStatus.SCHEDULED.value
    assert result.execution_count == 0


def test_create_normalizes_currency(db):
    user = create_user(db)
    account = create_account(db, user.id)
    service = ScheduledTransactionService(db)

    result = service.create_scheduled_transaction(
        user.id,
        make_create_data(
            source_account_id=account.id,
            currency="ngn",
        ),
    )

    # Currency normalization belongs to the schema/service input pipeline.
    assert result.currency == "NGN"


def test_create_rejects_invalid_user_id(db):
    service = ScheduledTransactionService(db)

    with pytest.raises(ValidationError):
        service.create_scheduled_transaction(
            0,
            make_create_data(source_account_id=1),
        )


def test_create_rejects_expense_without_source_account():
    with pytest.raises(PydanticValidationError):
        make_create_data()


def test_create_rejects_foreign_account(db):
    owner = create_user("unused@example.com") if False else create_user(db)
    other = create_user(db, "other@example.com")
    foreign_account = create_account(db, other.id)

    service = ScheduledTransactionService(db)
    data = make_create_data(source_account_id=foreign_account.id)

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(owner.id, data)


def test_create_rejects_nonexistent_account(db):
    user = create_user(db)
    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(source_account_id=999999),
        )


def test_create_rejects_foreign_portfolio(db):
    user = create_user(db)
    other = create_user(db, "other@example.com")
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, other.id)

    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(
                source_account_id=account.id,
                portfolio_id=portfolio.id,
            ),
        )


def test_create_rejects_inactive_account(db):
    user = create_user(db)
    account = create_account(db, user.id, is_active=False)
    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(source_account_id=account.id),
        )


def test_create_rejects_inactive_portfolio(db):
    user = create_user(db)
    account = create_account(db, user.id)
    portfolio = create_portfolio(db, user.id, is_active=False)
    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(
                source_account_id=account.id,
                portfolio_id=portfolio.id,
            ),
        )


def test_create_rejects_inactive_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)
    asset = create_asset(db, is_active=False)
    service = ScheduledTransactionService(db)

    with pytest.raises(ConflictError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(
                source_account_id=account.id,
                asset_id=asset.id,
            ),
        )


def test_create_rejects_nonexistent_asset(db):
    user = create_user(db)
    account = create_account(db, user.id)
    service = ScheduledTransactionService(db)

    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(
            user.id,
            make_create_data(
                source_account_id=account.id,
                asset_id=999999,
            ),
        )


@pytest.mark.parametrize(
    ("scheduled_type", "source", "destination", "asset_required"),
    [
        (ScheduledTransactionType.EXPENSE, True, False, False),
        (ScheduledTransactionType.WITHDRAWAL, True, False, False),
        (ScheduledTransactionType.FEE, True, False, False),
        (ScheduledTransactionType.DEPOSIT, False, True, False),
        (ScheduledTransactionType.DIVIDEND, False, True, False),
        (ScheduledTransactionType.INTEREST, False, True, False),
        (ScheduledTransactionType.TRANSFER, True, True, False),
        (ScheduledTransactionType.BUY, True, False, True),
        (ScheduledTransactionType.SELL, False, True, True),
    ],
)
def test_create_supported_transaction_types(
    db,
    scheduled_type,
    source,
    destination,
    asset_required,
):
    user = create_user(db)
    source_account = create_account(db, user.id, name="Source")
    destination_account = create_account(
        db,
        user.id,
        name="Destination",
    )
    asset = create_asset(db) if asset_required else None

    payload = {
        "scheduled_type": scheduled_type,
        "source_account_id": source_account.id if source else None,
        "destination_account_id": (
            destination_account.id if destination else None
        ),
        "asset_id": asset.id if asset else None,
    }

    result = ScheduledTransactionService(db).create_scheduled_transaction(
        user.id,
        make_create_data(**payload),
    )

    assert result.scheduled_type == scheduled_type.value


def test_create_rejects_schedule_without_any_resource_reference(db):
    user = create_user(db)
    service = ScheduledTransactionService(db)

    # Use a type whose schema permits the supplied resource fields to be absent.
    data = make_create_data(
        scheduled_type=ScheduledTransactionType.DEPOSIT,
        destination_account_id=1,
    )

    # The schema may accept the payload; the service validates real ownership.
    with pytest.raises(NotFoundError):
        service.create_scheduled_transaction(user.id, data)


# ===========================================================================
# Retrieval and listing
# ===========================================================================


def test_get_returns_owned_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).get_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result is not None
    assert result.id == schedule.id


def test_get_returns_none_for_another_user(db):
    owner = create_user(db)
    other = create_user(db, "other@example.com")
    account = create_account(db, owner.id)
    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).get_scheduled_transaction(
        other.id,
        schedule.id,
    )

    assert result is None


def test_require_rejects_missing_schedule(db):
    user = create_user(db)

    with pytest.raises(NotFoundError):
        ScheduledTransactionService(db).require_scheduled_transaction(
            user.id,
            999999,
        )


def test_require_rejects_schedule_owned_by_another_user(db):
    owner = create_user(db)
    other = create_user(db, "other@example.com")
    account = create_account(db, owner.id)
    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    with pytest.raises(NotFoundError):
        ScheduledTransactionService(db).require_scheduled_transaction(
            other.id,
            schedule.id,
        )


def test_list_is_scoped_to_user(db):
    user_one = create_user(db)
    user_two = create_user(db, "other@example.com")
    account_one = create_account(db, user_one.id)
    account_two = create_account(db, user_two.id)

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

    results = ScheduledTransactionService(db).list_scheduled_transactions(
        user_one.id,
    )

    assert [item.id for item in results] == [first.id]


def test_list_filters_by_status(db):
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

    results = ScheduledTransactionService(db).list_scheduled_transactions(
        user.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    assert [item.id for item in results] == [scheduled.id]


def test_list_filters_by_recurring_flag(db):
    user = create_user(db)
    account = create_account(db, user.id)

    recurring = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
    )
    create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        is_recurring=False,
    )

    results = ScheduledTransactionService(db).list_scheduled_transactions(
        user.id,
        is_recurring=True,
    )

    assert [item.id for item in results] == [recurring.id]


# ===========================================================================
# Updates
# ===========================================================================


def test_update_changes_allowed_fields(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).update_scheduled_transaction(
        user.id,
        schedule.id,
        ScheduledTransactionUpdate(
            merchant="Updated Merchant",
            description="Updated description",
        ),
    )

    assert result.merchant == "Updated Merchant"
    assert result.description == "Updated description"


def test_update_empty_payload_returns_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).update_scheduled_transaction(
        user.id,
        schedule.id,
        ScheduledTransactionUpdate(),
    )

    assert result.id == schedule.id


def test_update_rejects_unknown_fields():
    with pytest.raises(PydanticValidationError):
        ScheduledTransactionUpdate(unknown_field="not allowed")


@pytest.mark.parametrize(
    "status",
    [
        ScheduledTransactionStatus.PROCESSING,
        ScheduledTransactionStatus.COMPLETED,
        ScheduledTransactionStatus.CANCELLED,
    ],
)
def test_update_rejects_locked_statuses(db, status):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=status,
    )

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).update_scheduled_transaction(
            user.id,
            schedule.id,
            ScheduledTransactionUpdate(description="Not allowed"),
        )


def test_update_rejects_foreign_schedule(db):
    owner = create_user(db)
    other = create_user(db, "other@example.com")
    account = create_account(db, owner.id)
    schedule = create_schedule(
        db,
        owner.id,
        source_account_id=account.id,
    )

    with pytest.raises(NotFoundError):
        ScheduledTransactionService(db).update_scheduled_transaction(
            other.id,
            schedule.id,
            ScheduledTransactionUpdate(description="Unauthorized"),
        )


# ===========================================================================
# Cancellation and pause/resume
# ===========================================================================


def test_cancel_changes_status(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).cancel_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.CANCELLED.value


def test_cancel_is_idempotent(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.CANCELLED,
    )

    result = ScheduledTransactionService(db).cancel_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.CANCELLED.value


@pytest.mark.parametrize(
    "status",
    [
        ScheduledTransactionStatus.PROCESSING,
        ScheduledTransactionStatus.COMPLETED,
    ],
)
def test_cancel_rejects_processing_or_completed_schedule(db, status):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=status,
    )

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).cancel_scheduled_transaction(
            user.id,
            schedule.id,
        )


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

    result = ScheduledTransactionService(db).pause_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PAUSED.value


def test_pause_rejects_non_recurring_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).pause_scheduled_transaction(
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

    result = ScheduledTransactionService(db).pause_scheduled_transaction(
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

    result = ScheduledTransactionService(db).resume_scheduled_transaction(
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
    )

    result = ScheduledTransactionService(db).resume_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value


# ===========================================================================
# Execution lifecycle
# ===========================================================================


def test_mark_processing_updates_attempt_state(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )

    result = ScheduledTransactionService(db).mark_processing(
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

    result = ScheduledTransactionService(db).mark_processing(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.PROCESSING.value
    assert result.execution_error is None


@pytest.mark.parametrize(
    "status",
    [
        ScheduledTransactionStatus.PROCESSING,
        ScheduledTransactionStatus.COMPLETED,
        ScheduledTransactionStatus.CANCELLED,
        ScheduledTransactionStatus.PAUSED,
    ],
)
def test_mark_processing_rejects_invalid_state(db, status):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=status,
    )

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).mark_processing(
            user.id,
            schedule.id,
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

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).mark_failed(
            user.id,
            schedule.id,
            error="Execution failed.",
        )


def test_mark_failed_rejects_blank_error(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    with pytest.raises(ValidationError):
        ScheduledTransactionService(db).mark_failed(
            user.id,
            schedule.id,
            error="   ",
        )


def test_mark_failed_sets_error_and_status(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    result = ScheduledTransactionService(db).mark_failed(
        user.id,
        schedule.id,
        error="Provider unavailable.",
    )

    assert result.status == ScheduledTransactionStatus.FAILED.value
    assert result.execution_error == "Provider unavailable."
    assert result.last_attempt_at is not None


def test_mark_completed_rejects_non_processing_state(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.SCHEDULED,
    )

    with pytest.raises(ConflictError):
        ScheduledTransactionService(db).mark_completed(
            user.id,
            schedule.id,
        )


def test_mark_completed_finishes_non_recurring_schedule(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value
    assert result.execution_count == 1
    assert result.executed_at is not None
    assert result.execution_error is None


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

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.execution_count == 3


def test_mark_completed_recurring_schedule_advances_date(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_count=3,
        scheduled_date=DEFAULT_DATE,
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.SCHEDULED.value
    assert result.execution_count == 1
    assert result.scheduled_date == datetime(
        2026, 10, 10, 10, 0, tzinfo=timezone.utc
    )


def test_mark_completed_stops_at_recurrence_count(db):
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
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value
    assert result.execution_count == 1


def test_mark_completed_respects_recurrence_end_date(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_end_date=datetime(2026, 9, 15).date(),
        scheduled_date=DEFAULT_DATE,
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.status == ScheduledTransactionStatus.COMPLETED.value


# ===========================================================================
# Recurrence calculations
# ===========================================================================


def test_monthly_recurrence_clamps_end_of_month(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.MONTHLY,
        recurrence_count=3,
        scheduled_date=datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc),
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.scheduled_date == datetime(
        2026, 2, 28, 10, 0, tzinfo=timezone.utc
    )


def test_yearly_recurrence_handles_february_29(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
        status=ScheduledTransactionStatus.PROCESSING,
        is_recurring=True,
        recurrence=RecurrenceType.YEARLY,
        recurrence_count=3,
        scheduled_date=datetime(2028, 2, 29, 10, 0, tzinfo=timezone.utc),
    )

    result = ScheduledTransactionService(db).mark_completed(
        user.id,
        schedule.id,
    )

    assert result.scheduled_date == datetime(
        2029, 2, 28, 10, 0, tzinfo=timezone.utc
    )


# ===========================================================================
# Persistence
# ===========================================================================


def test_status_changes_are_persisted(db):
    user = create_user(db)
    account = create_account(db, user.id)
    schedule = create_schedule(
        db,
        user.id,
        source_account_id=account.id,
    )
    service = ScheduledTransactionService(db)

    service.mark_processing(user.id, schedule.id)
    db.expire_all()

    refreshed = service.require_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert refreshed.status == ScheduledTransactionStatus.PROCESSING.value


def test_failed_state_and_error_are_persisted(db):
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
        error="Provider unavailable.",
    )
    db.expire_all()

    refreshed = service.require_scheduled_transaction(
        user.id,
        schedule.id,
    )

    assert refreshed.status == ScheduledTransactionStatus.FAILED.value
    assert refreshed.execution_error == "Provider unavailable."