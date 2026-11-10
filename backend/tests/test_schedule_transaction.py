from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.models.scheduled_transaction import (
    RecurrenceType,
    ScheduledTransactionExecutionMode,
    ScheduledTransactionStatus,
    ScheduledTransactionType,
)
from backend.app.schemas.scheduled_transaction import (
    ScheduledTransactionCreate,
    ScheduledTransactionResponse,
    ScheduledTransactionSummary,
    ScheduledTransactionUpdate,
)


def future_date(days: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def make_valid_deposit(**overrides):
    data = {
        "scheduled_type": ScheduledTransactionType.DEPOSIT,
        "execution_mode": ScheduledTransactionExecutionMode.AMOUNT,
        "destination_account_id": 1,
        "amount": Decimal("1000.00"),
        "currency": "NGN",
        "scheduled_date": future_date(),
    }
    data.update(overrides)
    return data


def make_valid_buy(**overrides):
    data = {
        "scheduled_type": ScheduledTransactionType.BUY,
        "execution_mode": ScheduledTransactionExecutionMode.BOTH,
        "source_account_id": 1,
        "asset_id": 10,
        "amount": Decimal("500.00"),
        "currency": "USD",
        "quantity": Decimal("2"),
        "unit": "SHARE",
        "unit_price": Decimal("250.00"),
        "scheduled_date": future_date(),
    }
    data.update(overrides)
    return data


# ============================================================================
# ScheduledTransactionCreate — basic validation
# ============================================================================


def test_create_valid_amount_schedule():
    data = ScheduledTransactionCreate(**make_valid_deposit())

    assert data.scheduled_type == ScheduledTransactionType.DEPOSIT.value
    assert data.execution_mode == ScheduledTransactionExecutionMode.AMOUNT.value
    assert data.amount == Decimal("1000.00")
    assert data.currency == "NGN"
    assert data.destination_account_id == 1


def test_create_normalizes_currency():
    data = ScheduledTransactionCreate(
        **make_valid_deposit(currency=" usd ")
    )

    assert data.currency == "USD"


@pytest.mark.parametrize(
    "currency",
    [
        "",
        "US",
        "USDD",
        "12A",
        "123",
        "U$D",
        "US D",
    ],
)
def test_create_rejects_invalid_currency(currency):
    with pytest.raises(
        ValidationError,
        match="Currency must contain exactly three letters",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(currency=currency)
        )


def test_create_normalizes_unit():
    data = ScheduledTransactionCreate(
        **make_valid_buy(unit=" share ")
    )

    assert data.unit == "SHARE"


def test_create_strips_optional_strings():
    data = ScheduledTransactionCreate(
        **make_valid_deposit(
            merchant="  My Bank  ",
            external_reference="  REF-123  ",
            description="  Monthly deposit  ",
        )
    )

    assert data.merchant == "My Bank"
    assert data.external_reference == "REF-123"
    assert data.description == "Monthly deposit"


def test_create_blank_optional_strings_become_none():
    data = ScheduledTransactionCreate(
        **make_valid_deposit(
            merchant="   ",
            external_reference="   ",
            description="   ",
        )
    )

    assert data.merchant is None
    assert data.external_reference is None
    assert data.description is None


# ============================================================================
# Execution modes
# ============================================================================


def test_amount_mode_requires_amount():
    with pytest.raises(
        ValidationError,
        match="amount is required when execution_mode is AMOUNT",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(amount=None)
        )


def test_amount_mode_rejects_quantity():
    with pytest.raises(
        ValidationError,
        match="quantity must be omitted when execution_mode is AMOUNT",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                asset_id=10,
                quantity=Decimal("2"),
                unit="SHARE",
            )
        )


def test_quantity_mode_requires_quantity():
    with pytest.raises(
        ValidationError,
        match="quantity is required when execution_mode is QUANTITY",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(
                execution_mode=ScheduledTransactionExecutionMode.QUANTITY,
                amount=None,
                quantity=None,
                unit=None,
                unit_price=None,
            )
        )


def test_quantity_mode_rejects_amount():
    with pytest.raises(
        ValidationError,
        match="amount must be omitted when execution_mode is QUANTITY",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(
                execution_mode=ScheduledTransactionExecutionMode.QUANTITY,
                amount=Decimal("500"),
            )
        )


def test_both_mode_requires_amount():
    with pytest.raises(
        ValidationError,
        match="amount is required when execution_mode is BOTH",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(amount=None)
        )


def test_both_mode_requires_quantity():
    with pytest.raises(
        ValidationError,
        match="quantity is required when execution_mode is BOTH",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(quantity=None, unit=None)
        )


def test_both_mode_accepts_amount_and_quantity():
    data = ScheduledTransactionCreate(
        **make_valid_buy(
            amount=Decimal("1000"),
            quantity=Decimal("4"),
            unit_price=Decimal("250"),
        )
    )

    assert data.amount == Decimal("1000")
    assert data.quantity == Decimal("4")


# ============================================================================
# Asset requirements
# ============================================================================


@pytest.mark.parametrize(
    "scheduled_type",
    [
        ScheduledTransactionType.BUY,
        ScheduledTransactionType.SELL,
    ],
)
def test_buy_and_sell_require_asset(scheduled_type):
    if scheduled_type == ScheduledTransactionType.BUY:
        data = make_valid_buy(asset_id=None)
    else:
        data = {
            **make_valid_buy(),
            "scheduled_type": ScheduledTransactionType.SELL,
            "source_account_id": None,
            "destination_account_id": 2,
            "asset_id": None,
        }

    with pytest.raises(
        ValidationError,
        match="asset_id is required for BUY and SELL schedules",
    ):
        ScheduledTransactionCreate(**data)


def test_quantity_requires_asset():
    with pytest.raises(
        ValidationError,
        match="asset_id is required for BUY and SELL schedules",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(
                execution_mode=ScheduledTransactionExecutionMode.QUANTITY,
                amount=None,
                asset_id=None,
                quantity=Decimal("2"),
                unit="SHARE",
                unit_price=None,
            )
        )


def test_unit_requires_asset():
    with pytest.raises(
        ValidationError,
        match="unit cannot be specified without asset_id",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(unit="SHARE")
        )


def test_unit_price_requires_asset():
    with pytest.raises(
        ValidationError,
        match="unit_price cannot be specified without asset_id",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                unit_price=Decimal("250")
            )
        )


# ============================================================================
# Account requirements
# ============================================================================


def test_transfer_requires_source_account():
    with pytest.raises(
        ValidationError,
        match="source_account_id is required for TRANSFER",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.TRANSFER,
                source_account_id=None,
                destination_account_id=2,
            )
        )


def test_transfer_requires_destination_account():
    with pytest.raises(
        ValidationError,
        match="destination_account_id is required for TRANSFER",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.TRANSFER,
                source_account_id=1,
                destination_account_id=None,
            )
        )


def test_transfer_accounts_must_be_different():
    with pytest.raises(
        ValidationError,
        match=(
            "source_account_id and destination_account_id "
            "must be different"
        ),
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.TRANSFER,
                source_account_id=1,
                destination_account_id=1,
            )
        )


def test_deposit_requires_destination_account():
    with pytest.raises(
        ValidationError,
        match="destination_account_id is required for DEPOSIT",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(destination_account_id=None)
        )


def test_withdrawal_requires_source_account():
    with pytest.raises(
        ValidationError,
        match="source_account_id is required for WITHDRAWAL",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.WITHDRAWAL,
                source_account_id=None,
                destination_account_id=None,
            )
        )


def test_expense_requires_source_account():
    with pytest.raises(
        ValidationError,
        match="source_account_id is required for EXPENSE",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.EXPENSE,
                source_account_id=None,
                destination_account_id=None,
            )
        )


def test_buy_requires_source_account():
    with pytest.raises(
        ValidationError,
        match="source_account_id is required for BUY",
    ):
        ScheduledTransactionCreate(
            **make_valid_buy(source_account_id=None)
        )


def test_sell_requires_destination_account():
    data = make_valid_buy(
        scheduled_type=ScheduledTransactionType.SELL,
        source_account_id=None,
        destination_account_id=None,
    )

    with pytest.raises(
        ValidationError,
        match="destination_account_id is required for SELL",
    ):
        ScheduledTransactionCreate(**data)


def test_dividend_requires_destination_account():
    with pytest.raises(
        ValidationError,
        match="destination_account_id is required for DIVIDEND",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.DIVIDEND,
                asset_id=10,
                destination_account_id=None,
            )
        )


def test_interest_requires_destination_account():
    with pytest.raises(
        ValidationError,
        match="destination_account_id is required for INTEREST",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.INTEREST,
                destination_account_id=None,
            )
        )


def test_fee_requires_source_account():
    with pytest.raises(
        ValidationError,
        match="source_account_id is required for FEE",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_type=ScheduledTransactionType.FEE,
                source_account_id=None,
                destination_account_id=None,
            )
        )


# ============================================================================
# Recurrence
# ============================================================================


def test_non_recurring_schedule_is_valid_without_recurrence():
    data = ScheduledTransactionCreate(
        **make_valid_deposit(
            is_recurring=False,
            recurrence=None,
            recurrence_end_date=None,
            recurrence_count=None,
        )
    )

    assert data.is_recurring is False
    assert data.recurrence is None


def test_recurring_schedule_requires_recurrence():
    with pytest.raises(
        ValidationError,
        match="recurrence is required when is_recurring is True",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                is_recurring=True,
                recurrence=None,
            )
        )


def test_non_recurring_schedule_rejects_recurrence():
    with pytest.raises(
        ValidationError,
        match="recurrence must be None when is_recurring is False",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                is_recurring=False,
                recurrence=RecurrenceType.MONTHLY,
            )
        )


def test_non_recurring_schedule_rejects_recurrence_end_date():
    with pytest.raises(
        ValidationError,
        match="recurrence_end_date requires is_recurring to be True",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                is_recurring=False,
                recurrence_end_date=future_date(30),
            )
        )


def test_non_recurring_schedule_rejects_recurrence_count():
    with pytest.raises(
        ValidationError,
        match="recurrence_count requires is_recurring to be True",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                is_recurring=False,
                recurrence_count=5,
            )
        )


def test_recurrence_end_date_must_be_after_scheduled_date():
    scheduled_date = future_date(10)

    with pytest.raises(
        ValidationError,
        match="recurrence_end_date must be later than scheduled_date",
    ):
        ScheduledTransactionCreate(
            **make_valid_deposit(
                scheduled_date=scheduled_date,
                is_recurring=True,
                recurrence=RecurrenceType.MONTHLY,
                recurrence_end_date=scheduled_date,
            )
        )


def test_valid_recurring_schedule():
    scheduled_date = future_date(1)
    end_date = scheduled_date + timedelta(days=90)

    data = ScheduledTransactionCreate(
        **make_valid_deposit(
            scheduled_date=scheduled_date,
            is_recurring=True,
            recurrence=RecurrenceType.MONTHLY,
            recurrence_end_date=end_date,
            recurrence_count=3,
        )
    )

    assert data.is_recurring is True
    assert data.recurrence == RecurrenceType.MONTHLY.value
    assert data.recurrence_end_date == end_date
    assert data.recurrence_count == 3


# ============================================================================
# Numeric validation
# ============================================================================


def test_amount_must_be_positive():
    with pytest.raises(ValidationError):
        ScheduledTransactionCreate(
            **make_valid_deposit(amount=Decimal("0"))
        )


def test_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        ScheduledTransactionCreate(
            **make_valid_buy(quantity=Decimal("0"))
        )


def test_unit_price_must_be_positive():
    with pytest.raises(ValidationError):
        ScheduledTransactionCreate(
            **make_valid_buy(unit_price=Decimal("0"))
        )


# ============================================================================
# ScheduledTransactionUpdate
#
# Important:
# Update is a PATCH schema. It intentionally does NOT validate the complete
# transaction configuration by itself. The service must merge the supplied
# fields with the existing record and then validate the resulting state.
# ============================================================================


def test_update_allows_partial_payload():
    data = ScheduledTransactionUpdate(
        amount=Decimal("2500")
    )

    assert data.amount == Decimal("2500")
    assert data.currency is None
    assert data.scheduled_type is None
    assert data.execution_mode is None


def test_update_allows_multiple_partial_fields():
    data = ScheduledTransactionUpdate(
        amount=Decimal("2500"),
        currency=" usd ",
        merchant="  Binance  ",
    )

    assert data.amount == Decimal("2500")
    assert data.currency == "USD"
    assert data.merchant == "Binance"


def test_update_normalizes_unit():
    data = ScheduledTransactionUpdate(unit=" share ")

    assert data.unit == "SHARE"


def test_update_normalizes_optional_strings():
    data = ScheduledTransactionUpdate(
        merchant="  Merchant  ",
        external_reference="  REF-1  ",
        description="  Description  ",
    )

    assert data.merchant == "Merchant"
    assert data.external_reference == "REF-1"
    assert data.description == "Description"


def test_update_rejects_invalid_currency():
    with pytest.raises(
        ValidationError,
        match="Currency must contain exactly three letters",
    ):
        ScheduledTransactionUpdate(currency="US")


def test_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ScheduledTransactionUpdate(
            unknown_field="value"
        )


def test_update_allows_explicit_null_values():
    data = ScheduledTransactionUpdate(
        merchant=None,
        description=None,
        recurrence=None,
    )

    assert data.merchant is None
    assert data.description is None
    assert data.recurrence is None


def test_update_rejects_non_positive_amount():
    with pytest.raises(ValidationError):
        ScheduledTransactionUpdate(
            amount=Decimal("0")
        )


def test_update_rejects_non_positive_quantity():
    with pytest.raises(ValidationError):
        ScheduledTransactionUpdate(
            quantity=Decimal("0")
        )


def test_update_rejects_non_positive_unit_price():
    with pytest.raises(ValidationError):
        ScheduledTransactionUpdate(
            unit_price=Decimal("0")
        )


# ============================================================================
# Response schema
# ============================================================================


def test_response_accepts_valid_data():
    response = ScheduledTransactionResponse(
        id=1,
        user_id=1,
        scheduled_type=ScheduledTransactionType.DEPOSIT,
        execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
        status=ScheduledTransactionStatus.SCHEDULED,
        destination_account_id=2,
        amount=Decimal("1000"),
        currency="NGN",
        scheduled_date=future_date(),
        is_recurring=False,
        execution_count=0,
        last_attempt_at=None,
        executed_at=None,
        execution_error=None,
        created_at=future_date(),
        updated_at=future_date(),
    )

    assert response.id == 1
    assert response.user_id == 1
    assert response.status == ScheduledTransactionStatus.SCHEDULED.value
    assert response.execution_count == 0


def test_response_rejects_non_positive_id():
    with pytest.raises(ValidationError):
        ScheduledTransactionResponse(
            id=0,
            user_id=1,
            scheduled_type=ScheduledTransactionType.DEPOSIT,
            execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
            status=ScheduledTransactionStatus.SCHEDULED,
            amount=Decimal("1000"),
            currency="NGN",
            scheduled_date=future_date(),
            is_recurring=False,
            execution_count=0,
            created_at=future_date(),
            updated_at=future_date(),
        )


def test_response_rejects_negative_execution_count():
    with pytest.raises(ValidationError):
        ScheduledTransactionResponse(
            id=1,
            user_id=1,
            scheduled_type=ScheduledTransactionType.DEPOSIT,
            execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
            status=ScheduledTransactionStatus.SCHEDULED,
            amount=Decimal("1000"),
            currency="NGN",
            scheduled_date=future_date(),
            is_recurring=False,
            execution_count=-1,
            created_at=future_date(),
            updated_at=future_date(),
        )


# ============================================================================
# Summary schema
# ============================================================================


def test_summary_accepts_valid_data():
    summary = ScheduledTransactionSummary(
        id=1,
        user_id=1,
        scheduled_type=ScheduledTransactionType.DEPOSIT,
        execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
        status=ScheduledTransactionStatus.SCHEDULED,
        amount=Decimal("1000"),
        currency="NGN",
        quantity=None,
        unit=None,
        unit_price=None,
        asset_id=None,
        source_account_id=None,
        destination_account_id=2,
        scheduled_date=future_date(),
        is_recurring=False,
        recurrence=None,
        execution_count=0,
        executed_at=None,
    )

    assert summary.id == 1
    assert summary.user_id == 1
    assert summary.scheduled_type == ScheduledTransactionType.DEPOSIT.value
    assert summary.execution_mode == ScheduledTransactionExecutionMode.AMOUNT.value
    assert summary.status == ScheduledTransactionStatus.SCHEDULED.value
    assert summary.execution_count == 0


def test_summary_rejects_negative_execution_count():
    with pytest.raises(ValidationError):
        ScheduledTransactionSummary(
            id=1,
            user_id=1,
            scheduled_type=ScheduledTransactionType.DEPOSIT,
            execution_mode=ScheduledTransactionExecutionMode.AMOUNT,
            status=ScheduledTransactionStatus.SCHEDULED,
            amount=Decimal("1000"),
            currency="NGN",
            scheduled_date=future_date(),
            is_recurring=False,
            execution_count=-1,
        )