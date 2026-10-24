from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression, func

from app.database.connection import Base


# ============================================================
# ENUMS
# ============================================================


class ScheduledTransactionType(str, Enum):
    """
    Defines the financial event that Finova intends to execute.

    These values intentionally use the same vocabulary as
    TransactionType so that a scheduled action can eventually
    produce a normal Transaction without introducing a second
    incompatible transaction vocabulary.
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
    Defines what the user fixes when creating the schedule.

    AMOUNT:
        The user specifies how much money should be used.

        Example:
            Buy ₦100,000 of an asset every month.

        The actual quantity is determined using the price
        available at execution time.

    QUANTITY:
        The user specifies how many units should be acquired
        or disposed of.

        Example:
            Buy 20 shares every month.

        The actual monetary amount is determined using the
        execution price.

    A schedule must use exactly one of these modes.

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

    SCHEDULED:
        Waiting for its next execution date.

    PROCESSING:
        An execution attempt is currently being processed.

    COMPLETED:
        The schedule has completed successfully.

        For recurring schedules, this represents a schedule whose
        current execution has completed successfully. The scheduler
        may subsequently move it back into SCHEDULED for its next
        occurrence.

    FAILED:
        The most recent execution attempt failed.

        Failure information is retained for retry, notification,
        and audit purposes.

    CANCELLED:
        The schedule has been permanently cancelled.

    PAUSED:
        The schedule has been intentionally disabled without being
        permanently cancelled.
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
# MODEL
# ============================================================


class ScheduledTransaction(Base):
    """
    Represents a financial action that Finova intends to execute
    at a future date or according to a recurring schedule.

    A ScheduledTransaction represents USER INTENT.

    It does not represent money that has already moved.

    Once execution successfully occurs, Finova creates a normal
    Transaction representing what actually happened.

    Examples:

        - Transfer ₦100,000 from one account to another.
        - Buy 20 shares of an asset.
        - Buy ₦50,000 worth of an asset.
        - Pay a recurring subscription as an EXPENSE.
        - Transfer money to an investment account every month.

    IMPORTANT ARCHITECTURAL DISTINCTION:

        ScheduledTransaction
            = what should happen

        Transaction
            = what actually happened

    Market-backed scheduled investments use the live market price
    available at execution time.

    Therefore a reference unit_price stored here must NEVER be
    interpreted as a guaranteed execution price.
    """

    __tablename__ = "scheduled_transactions"

    # ============================================================
    # TABLE INDEXES
    # ============================================================

    __table_args__ = (

        # Find a user's schedules ordered by next execution.
        Index(
            "ix_scheduled_transactions_user_scheduled_date",
            "user_id",
            "scheduled_date",
        ),

        # Efficiently find schedules that need processing.
        Index(
            "ix_scheduled_transactions_status_scheduled_date",
            "status",
            "scheduled_date",
        ),

        # Portfolio scheduling history.
        Index(
            "ix_scheduled_transactions_portfolio_scheduled_date",
            "portfolio_id",
            "scheduled_date",
        ),

        # Source-account scheduling history.
        Index(
            "ix_scheduled_transactions_source_account_scheduled_date",
            "source_account_id",
            "scheduled_date",
        ),

        # Destination-account scheduling history.
        Index(
            "ix_scheduled_transactions_destination_account_scheduled_date",
            "destination_account_id",
            "scheduled_date",
        ),

        # Filter schedules by action type and lifecycle state.
        Index(
            "ix_scheduled_transactions_type_status",
            "scheduled_type",
            "status",
        ),
    )

    # ============================================================
    # PRIMARY KEY
    # ============================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ============================================================
    # OWNERSHIP
    # ============================================================

    # User who owns the scheduled financial action.
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ============================================================
    # PORTFOLIO
    # ============================================================

    # Portfolio affected by the scheduled action.
    #
    # Nullable because many scheduled actions are account-level,
    # such as expenses, subscriptions, and bank transfers.
    portfolio_id = Column(
        Integer,
        ForeignKey(
            "portfolios.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # ============================================================
    # SOURCE ACCOUNT
    # ============================================================

    # Account from which money/assets originate.
    source_account_id = Column(
        Integer,
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # ============================================================
    # DESTINATION ACCOUNT
    # ============================================================

    # Account receiving money/assets.
    destination_account_id = Column(
        Integer,
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # ============================================================
    # ASSET
    # ============================================================

    # Asset involved in the scheduled action.
    #
    # Examples:
    #   AAPL
    #   BTC
    #   GOLD
    #
    # Nullable because expenses and ordinary transfers may not
    # involve an investment asset.
    asset_id = Column(
        Integer,
        ForeignKey(
            "assets.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # ============================================================
    # SCHEDULED TRANSACTION TYPE
    # ============================================================

    # Defines what Finova intends to do.
    scheduled_type = Column(
        String(30),
        nullable=False,
        index=True,
    )

    # ============================================================
    # EXECUTION MODE
    # ============================================================

    # Determines what the user fixed when creating the schedule.
    #
    # AMOUNT:
    #     amount is supplied and quantity is calculated at execution.
    #
    # QUANTITY:
    #     quantity is supplied and amount is calculated at execution.
    #
    # Business/schema validation will enforce the relationship
    # between execution_mode, amount, and quantity.
    execution_mode = Column(
        String(20),
        nullable=False,
        index=True,
    )

    # ============================================================
    # STATUS
    # ============================================================

    # Current lifecycle state of the schedule.
    status = Column(
        String(20),
        nullable=False,
        default=ScheduledTransactionStatus.SCHEDULED.value,
        server_default=ScheduledTransactionStatus.SCHEDULED.value,
        index=True,
    )

    # ============================================================
    # RECURRENCE
    # ============================================================

    # Whether this schedule repeats.
    is_recurring = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
        index=True,
    )

    # Recurrence frequency.
    #
    # NULL for one-time schedules.
    recurrence = Column(
        String(20),
        nullable=True,
    )

    # Optional date/time after which recurrence stops.
    recurrence_end_date = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Optional maximum number of successful executions.
    #
    # Example:
    #     Invest ₦100,000 monthly for 12 successful executions.
    recurrence_count = Column(
        Integer,
        nullable=True,
    )

    # Number of successful executions completed.
    #
    # This is schedule state and is not a replacement for the
    # historical Transaction records generated by execution.
    execution_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ============================================================
    # FINANCIAL VALUE
    # ============================================================

    # Monetary amount specified by the user when using AMOUNT mode.
    #
    # NULL is valid for QUANTITY mode because the final monetary
    # value is determined from the execution price.
    amount = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # Currency associated with the monetary amount.
    currency = Column(
        String(3),
        nullable=False,
    )

    # ============================================================
    # ASSET QUANTITY
    # ============================================================

    # Quantity specified by the user when using QUANTITY mode.
    #
    # NULL is valid for AMOUNT mode because the actual quantity
    # is calculated at execution time.
    quantity = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # Unit associated with quantity.
    #
    # Examples:
    #   SHARE
    #   BTC
    #   GRAM
    #   UNIT
    unit = Column(
        String(30),
        nullable=True,
    )

    # ============================================================
    # REFERENCE PRICE
    # ============================================================

    # Reference/observed price when the schedule is created or
    # otherwise configured.
    #
    # IMPORTANT:
    #
    # This is NOT the guaranteed execution price.
    #
    # For market-backed assets, the actual execution price must
    # come from the market-data/execution process at execution time.
    #
    # Example:
    #
    #     Schedule created:
    #         AAPL = $200
    #
    #     unit_price = $200
    #
    #     Execution later:
    #         AAPL = $215
    #
    #     Actual Transaction:
    #         unit_price = $215
    unit_price = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # ============================================================
    # MERCHANT / COUNTERPARTY
    # ============================================================

    merchant = Column(
        String(255),
        nullable=True,
    )

    # ============================================================
    # EXTERNAL REFERENCE
    # ============================================================

    # External reference supplied by another system/provider.
    #
    # Intentionally NOT globally unique.
    #
    # As with Transaction.external_reference, the correct
    # uniqueness boundary depends on the eventual provider/import
    # architecture.
    external_reference = Column(
        String(255),
        nullable=True,
        index=True,
    )

    # ============================================================
    # DESCRIPTION
    # ============================================================

    description = Column(
        Text,
        nullable=True,
    )

    # ============================================================
    # SCHEDULING
    # ============================================================

    # Next date/time at which the schedule should be considered
    # for execution.
    #
    # ONE-TIME:
    #     Intended execution date.
    #
    # RECURRING:
    #     Next execution date.
    scheduled_date = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # ============================================================
    # EXECUTION INFORMATION
    # ============================================================

    # Time of the most recent execution attempt.
    last_attempt_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Time of the most recent successful execution.
    #
    # For recurring schedules this is updated after every
    # successful occurrence.
    executed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ============================================================
    # FAILURE INFORMATION
    # ============================================================

    # Human-readable information about the most recent failed
    # execution attempt.
    execution_error = Column(
        Text,
        nullable=True,
    )

    # ============================================================
    # RECORD TIMESTAMPS
    # ============================================================

    # When the schedule record was created.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When the schedule record was last modified.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ============================================================
    # RELATIONSHIPS
    # ============================================================

    user = relationship(
        "User",
        back_populates="scheduled_transactions",
    )

    portfolio = relationship(
        "Portfolio",
        back_populates="scheduled_transactions",
    )

    asset = relationship(
        "Asset",
        back_populates="scheduled_transactions",
    )

    source_account = relationship(
        "Account",
        foreign_keys=[source_account_id],
        back_populates="scheduled_source_transactions",
    )

    destination_account = relationship(
        "Account",
        foreign_keys=[destination_account_id],
        back_populates="scheduled_destination_transactions",
    )

    # One scheduled action can generate many actual Transactions.
    #
    # Example:
    #
    # ScheduledTransaction #15
    #     ├── Transaction #101
    #     ├── Transaction #134
    #     └── Transaction #167
    #
    # This is especially important for recurring schedules.
    transactions = relationship(
        "Transaction",
        back_populates="scheduled_transaction",
    )