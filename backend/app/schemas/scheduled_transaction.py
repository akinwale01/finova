from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ============================================================
# ENUMS
# ============================================================


class ScheduledTransactionType(str, Enum):
    """
    Defines the financial event that Finova intends to execute.

    These values intentionally mirror TransactionType so that a
    scheduled action can eventually produce a normal Transaction
    without translating between incompatible vocabularies.
    """

    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    EXPENSE = "EXPENSE"
    TRANSFER = "TRANSFER"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"


class ScheduledTransactionExecutionMode(str, Enum):
    """
    Defines what the user specifies for execution.

    AMOUNT:
        The user specifies the monetary amount.

        Example:
            Buy ₦50,000 of AAPL.

        At execution time, Finova obtains the executable price
        and determines the resulting quantity.

    QUANTITY:
        The user specifies the asset quantity.

        Example:
            Buy 20 AAPL shares.

        At execution time, Finova obtains the executable price
        and determines the resulting monetary amount.

    BOTH:
        The schedule stores both amount and quantity as part of
        the scheduled instruction/reference.

        Neither value represents a guaranteed execution result.

        The actual Transaction records the values produced at
        execution time.
    """

    AMOUNT = "AMOUNT"
    QUANTITY = "QUANTITY"
    BOTH = "BOTH"


class ScheduledTransactionStatus(str, Enum):
    """
    Defines the lifecycle state of a scheduled transaction.
    """

    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class RecurrenceType(str, Enum):
    """
    Defines how a scheduled transaction repeats.
    """

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


# ============================================================
# BASE SCHEMA
# ============================================================


class ScheduledTransactionBase(BaseModel):
    """
    Shared validation and fields for ScheduledTransaction
    creation and response schemas.

    This represents the user-configurable definition of a
    scheduled financial action.

    Execution-engine state such as status, execution_count,
    last_attempt_at, executed_at, and execution_error is not
    controlled through this base configuration.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    # ========================================================
    # PORTFOLIO / ACCOUNTS / ASSET
    # ========================================================

    portfolio_id: int | None = Field(
        default=None,
        gt=0,
        description="Portfolio affected by the scheduled action.",
    )

    source_account_id: int | None = Field(
        default=None,
        gt=0,
        description="Account from which money or assets originate.",
    )

    destination_account_id: int | None = Field(
        default=None,
        gt=0,
        description="Account receiving money or assets.",
    )

    asset_id: int | None = Field(
        default=None,
        gt=0,
        description="Asset involved in the scheduled action.",
    )

    # ========================================================
    # ACTION
    # ========================================================

    scheduled_type: ScheduledTransactionType = Field(
        description="Financial action Finova intends to execute.",
    )

    execution_mode: ScheduledTransactionExecutionMode = Field(
        description=(
            "Determines whether the user specifies an amount, "
            "quantity, or both."
        ),
    )

    # ========================================================
    # FINANCIAL VALUE
    # ========================================================

    amount: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
        description=(
            "Monetary amount specified by the scheduled instruction."
        ),
    )

    currency: str = Field(
        description="Three-letter currency code.",
    )

    # ========================================================
    # ASSET QUANTITY
    # ========================================================

    quantity: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
        description=(
            "Asset quantity specified by the scheduled instruction."
        ),
    )

    unit: str | None = Field(
        default=None,
        max_length=30,
        description="Unit associated with the asset quantity.",
    )

    # ========================================================
    # REFERENCE PRICE
    # ========================================================

    unit_price: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
        description=(
            "Observed/reference asset price when the schedule was "
            "created or configured. This is informational and "
            "does not guarantee the eventual execution price."
        ),
    )

    # ========================================================
    # MERCHANT / EXTERNAL REFERENCE
    # ========================================================

    merchant: str | None = Field(
        default=None,
        max_length=255,
    )

    external_reference: str | None = Field(
        default=None,
        max_length=255,
    )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    # ========================================================
    # SCHEDULING
    # ========================================================

    scheduled_date: datetime = Field(
        description=(
            "Next date/time at which the schedule should be "
            "considered for execution."
        ),
    )

    is_recurring: bool = Field(
        default=False,
        description="Whether the scheduled action repeats.",
    )

    recurrence: RecurrenceType | None = Field(
        default=None,
        description="Recurrence frequency for recurring schedules.",
    )

    recurrence_end_date: datetime | None = Field(
        default=None,
        description="Optional date after which recurrence stops.",
    )

    recurrence_count: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional maximum number of successful executions."
        ),
    )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        """
        Normalize and validate a currency code.

        Whitespace is removed before validation so values such as
        " ngn " are normalized to "NGN".
        """
        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "Currency must contain exactly three letters."
            )

        return value

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        """
        Normalize quantity units to uppercase.
        """
        if value is None:
            return None

        value = value.strip()

        return value.upper() or None

    @field_validator(
        "merchant",
        "external_reference",
        "description",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Trim optional strings and convert whitespace-only values
        to None.
        """
        if value is None:
            return None

        value = value.strip()

        return value or None

    # ========================================================
    # EXECUTION-MODE VALIDATION
    # ========================================================

    @model_validator(mode="after")
    def validate_execution_definition(self):
        """
        Validate the financial information required by the
        selected execution mode.

        AMOUNT:
            amount is required.
            quantity is not supplied.

        QUANTITY:
            quantity is required.
            amount is not supplied.

        BOTH:
            both amount and quantity are required.

        unit_price remains independent because it is only a
        reference value and never a guaranteed execution price.
        """

        if self.execution_mode == ScheduledTransactionExecutionMode.AMOUNT:

            if self.amount is None:
                raise ValueError(
                    "amount is required when execution_mode is AMOUNT."
                )

            if self.quantity is not None:
                raise ValueError(
                    "quantity must be omitted when execution_mode is AMOUNT."
                )

        elif self.execution_mode == ScheduledTransactionExecutionMode.QUANTITY:

            if self.quantity is None:
                raise ValueError(
                    "quantity is required when execution_mode is QUANTITY."
                )

            if self.amount is not None:
                raise ValueError(
                    "amount must be omitted when execution_mode is QUANTITY."
                )

        elif self.execution_mode == ScheduledTransactionExecutionMode.BOTH:

            if self.amount is None:
                raise ValueError(
                    "amount is required when execution_mode is BOTH."
                )

            if self.quantity is None:
                raise ValueError(
                    "quantity is required when execution_mode is BOTH."
                )

        return self

    # ========================================================
    # ASSET VALIDATION
    # ========================================================

    @model_validator(mode="after")
    def validate_asset_requirements(self):
        """
        Validate fields that depend on whether an asset is involved.

        BUY and SELL always require an asset.

        Quantity, unit, and reference unit price are asset-specific
        fields and therefore cannot be supplied without an asset.
        """

        asset_transaction_types = {
            ScheduledTransactionType.BUY,
            ScheduledTransactionType.SELL,
        }

        if (
            self.scheduled_type in asset_transaction_types
            and self.asset_id is None
        ):
            raise ValueError(
                "asset_id is required for BUY and SELL schedules."
            )

        if self.quantity is not None and self.asset_id is None:
            raise ValueError(
                "quantity cannot be specified without asset_id."
            )

        if self.unit is not None and self.asset_id is None:
            raise ValueError(
                "unit cannot be specified without asset_id."
            )

        if self.unit_price is not None and self.asset_id is None:
            raise ValueError(
                "unit_price cannot be specified without asset_id."
            )

        return self

    # ========================================================
    # ACCOUNT VALIDATION
    # ========================================================

    @model_validator(mode="after")
    def validate_account_requirements(self):
        """
        Validate account relationships required by the financial
        action.

        TRANSFER:
            Requires both source and destination accounts, and
            they must be different.

        DEPOSIT:
            Requires a destination account.

        WITHDRAWAL:
            Requires a source account.

        EXPENSE:
            Requires a source account.

        BUY:
            Requires a source account.

        SELL:
            Requires a destination account.

        DIVIDEND:
            Requires a destination account.

        INTEREST:
            Requires a destination account.

        FEE:
            Requires a source account.
        """

        if self.scheduled_type == ScheduledTransactionType.TRANSFER:

            if self.source_account_id is None:
                raise ValueError(
                    "source_account_id is required for TRANSFER."
                )

            if self.destination_account_id is None:
                raise ValueError(
                    "destination_account_id is required for TRANSFER."
                )

            if self.source_account_id == self.destination_account_id:
                raise ValueError(
                    "source_account_id and destination_account_id "
                    "must be different."
                )

        elif self.scheduled_type == ScheduledTransactionType.DEPOSIT:

            if self.destination_account_id is None:
                raise ValueError(
                    "destination_account_id is required for DEPOSIT."
                )

        elif self.scheduled_type == ScheduledTransactionType.WITHDRAWAL:

            if self.source_account_id is None:
                raise ValueError(
                    "source_account_id is required for WITHDRAWAL."
                )

        elif self.scheduled_type == ScheduledTransactionType.EXPENSE:

            if self.source_account_id is None:
                raise ValueError(
                    "source_account_id is required for EXPENSE."
                )

        elif self.scheduled_type == ScheduledTransactionType.BUY:

            if self.source_account_id is None:
                raise ValueError(
                    "source_account_id is required for BUY."
                )

        elif self.scheduled_type == ScheduledTransactionType.SELL:

            if self.destination_account_id is None:
                raise ValueError(
                    "destination_account_id is required for SELL."
                )

        elif self.scheduled_type == ScheduledTransactionType.DIVIDEND:

            if self.destination_account_id is None:
                raise ValueError(
                    "destination_account_id is required for DIVIDEND."
                )

        elif self.scheduled_type == ScheduledTransactionType.INTEREST:

            if self.destination_account_id is None:
                raise ValueError(
                    "destination_account_id is required for INTEREST."
                )

        elif self.scheduled_type == ScheduledTransactionType.FEE:

            if self.source_account_id is None:
                raise ValueError(
                    "source_account_id is required for FEE."
                )

        return self

    # ========================================================
    # RECURRENCE VALIDATION
    # ========================================================

    @model_validator(mode="after")
    def validate_recurrence_definition(self):
        """
        Keep recurrence fields internally consistent.

        One-time schedules:
            recurrence fields must be absent.

        Recurring schedules:
            recurrence is required.

        recurrence_end_date must occur after the current scheduled
        execution date.
        """

        if self.is_recurring:

            if self.recurrence is None:
                raise ValueError(
                    "recurrence is required when is_recurring is True."
                )

        else:

            if self.recurrence is not None:
                raise ValueError(
                    "recurrence must be None when is_recurring is False."
                )

            if self.recurrence_end_date is not None:
                raise ValueError(
                    "recurrence_end_date requires "
                    "is_recurring to be True."
                )

            if self.recurrence_count is not None:
                raise ValueError(
                    "recurrence_count requires "
                    "is_recurring to be True."
                )

        if (
            self.recurrence_end_date is not None
            and self.recurrence_end_date <= self.scheduled_date
        ):
            raise ValueError(
                "recurrence_end_date must be later than scheduled_date."
            )

        return self


# ============================================================
# CREATE SCHEMA
# ============================================================


class ScheduledTransactionCreate(ScheduledTransactionBase):
    """
    Schema used when creating a scheduled transaction.

    user_id is intentionally excluded.

    Ownership must come from the authenticated user rather than
    client-supplied request data.
    """

    pass


# ============================================================
# UPDATE SCHEMA
# ============================================================


class ScheduledTransactionUpdate(BaseModel):
    """
    Schema used for PATCH-style updates.

    Every user-configurable field is optional.

    Backend execution state is intentionally excluded.

    The service layer must:

        1. Load the existing schedule.
        2. Extract only explicitly supplied fields.
        3. Merge those fields with the existing configuration.
        4. Validate the complete merged configuration.
        5. Persist the result.

    This preserves the distinction between an omitted field and
    an explicitly supplied None.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=True,
        extra="forbid",
    )

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    portfolio_id: int | None = Field(
        default=None,
        gt=0,
    )

    source_account_id: int | None = Field(
        default=None,
        gt=0,
    )

    destination_account_id: int | None = Field(
        default=None,
        gt=0,
    )

    asset_id: int | None = Field(
        default=None,
        gt=0,
    )

    # ========================================================
    # ACTION
    # ========================================================

    scheduled_type: ScheduledTransactionType | None = None

    execution_mode: ScheduledTransactionExecutionMode | None = None

    # ========================================================
    # FINANCIAL VALUE
    # ========================================================

    amount: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
    )

    currency: str | None = Field(
        default=None,
    )

    quantity: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
    )

    unit: str | None = Field(
        default=None,
        max_length=30,
    )

    unit_price: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=20,
        decimal_places=8,
    )

    # ========================================================
    # DETAILS
    # ========================================================

    merchant: str | None = Field(
        default=None,
        max_length=255,
    )

    external_reference: str | None = Field(
        default=None,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    # ========================================================
    # SCHEDULING
    # ========================================================

    scheduled_date: datetime | None = None

    is_recurring: bool | None = None

    recurrence: RecurrenceType | None = None

    recurrence_end_date: datetime | None = None

    recurrence_count: int | None = Field(
        default=None,
        gt=0,
    )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @field_validator("currency")
    @classmethod
    def normalize_currency(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize and validate an optional currency code.
        """
        if value is None:
            return None

        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "Currency must contain exactly three letters."
            )

        return value

    @field_validator("unit")
    @classmethod
    def normalize_unit(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize quantity units to uppercase.
        """
        if value is None:
            return None

        value = value.strip()

        return value.upper() or None

    @field_validator(
        "merchant",
        "external_reference",
        "description",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Trim optional strings and convert whitespace-only values
        to None.
        """
        if value is None:
            return None

        value = value.strip()

        return value or None


# ============================================================
# RESPONSE SCHEMA
# ============================================================


class ScheduledTransactionResponse(ScheduledTransactionBase):
    """
    Public API representation of a ScheduledTransaction.

    Includes backend-generated and execution-state fields that
    clients may read but must not directly control.
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    id: int = Field(gt=0)

    user_id: int = Field(gt=0)

    status: ScheduledTransactionStatus

    execution_count: int = Field(ge=0)

    last_attempt_at: datetime | None = None

    executed_at: datetime | None = None

    execution_error: str | None = None

    created_at: datetime

    updated_at: datetime


# ============================================================
# LIST / SUMMARY RESPONSE
# ============================================================


class ScheduledTransactionSummary(BaseModel):
    """
    Lightweight representation for list endpoints.

    Used when the frontend needs schedule information without
    loading the complete response representation.
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    id: int = Field(gt=0)

    user_id: int = Field(gt=0)

    scheduled_type: ScheduledTransactionType

    execution_mode: ScheduledTransactionExecutionMode

    status: ScheduledTransactionStatus

    amount: Decimal | None = None

    currency: str

    quantity: Decimal | None = None

    unit: str | None = None

    unit_price: Decimal | None = None

    asset_id: int | None = None

    source_account_id: int | None = None

    destination_account_id: int | None = None

    scheduled_date: datetime

    is_recurring: bool

    recurrence: RecurrenceType | None = None

    execution_count: int = Field(ge=0)

    executed_at: datetime | None = None