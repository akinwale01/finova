from enum import Enum

from backend.app.database.connection import Base
from sqlalchemy import (
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
from sqlalchemy.sql import func


class TransactionType(str, Enum):
    """
    Defines the financial event represented by a transaction.

    These values are stored as normalized uppercase strings
    in the database and controlled by the application layer.
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


class TransactionStatus(str, Enum):
    """
    Defines the execution state of a transaction.

    COMPLETED:
        The financial event successfully occurred and therefore
        affects the user's financial position.

    FAILED:
        The transaction was attempted but did not successfully
        execute.

    CANCELLED:
        The transaction was cancelled before successful
        completion.

    FAILED and CANCELLED transactions are retained for
    audit/history purposes but are excluded from completed
    financial calculations.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Transaction(Base):
    """
    Represents a financial event recorded by Finova.

    A Transaction records what financially happened.

    Examples:
        - Buying an investment
        - Selling an investment
        - Depositing money
        - Withdrawing money
        - Paying for groceries
        - Paying a subscription
        - ATM withdrawal
        - POS payment
        - Transferring money between accounts
        - Receiving dividends
        - Receiving interest
        - Paying investment/banking fees

    Scheduled/future transactions are handled separately by
    ScheduledTransaction.

    Once a scheduled transaction successfully executes,
    Finova creates a normal Transaction record.

    IMPORTANT STATUS BEHAVIOR:

        COMPLETED:
            The transaction successfully occurred and is
            eligible to affect financial calculations.

        FAILED:
            The attempted transaction did not successfully
            execute. It remains available for audit/history
            but must not affect completed financial calculations.

        CANCELLED:
            The transaction was cancelled before successful
            completion. It remains available for audit/history
            but must not affect completed financial calculations.

    IMPORTANT EXTERNAL REFERENCE BEHAVIOR:

        external_reference is intentionally NOT globally unique
        at this stage.

        Finova has not yet established the external-provider
        architecture and therefore has not established the
        correct uniqueness boundary.

        The field remains nullable and indexed so it can be
        efficiently used for reconciliation and lookup.

        A database-level uniqueness constraint will be added
        only after the external-provider/import architecture
        establishes whether uniqueness belongs to:

            provider + external_reference
            account + external_reference
            another provider-specific scope

        Do NOT treat external_reference alone as a globally
        unique transaction identifier.
    """

    __tablename__ = "transactions"

    # =========================================================
    # TABLE INDEXES
    # =========================================================

    __table_args__ = (

        # -----------------------------------------------------
        # Portfolio transaction history.
        # -----------------------------------------------------
        Index(
            "ix_transactions_portfolio_date",
            "portfolio_id",
            "transaction_date",
        ),

        # -----------------------------------------------------
        # Source-account transaction history.
        # -----------------------------------------------------
        Index(
            "ix_transactions_source_account_date",
            "source_account_id",
            "transaction_date",
        ),

        # -----------------------------------------------------
        # Destination-account transaction history.
        # -----------------------------------------------------
        Index(
            "ix_transactions_destination_account_date",
            "destination_account_id",
            "transaction_date",
        ),

        # -----------------------------------------------------
        # Transaction filtering by event type and execution
        # status.
        # -----------------------------------------------------
        Index(
            "ix_transactions_type_status",
            "transaction_type",
            "status",
        ),
    )

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # PORTFOLIO
    # =========================================================

    # Portfolio affected by the transaction.
    #
    # Nullable because many transactions are account-level
    # activities and do not involve an investment portfolio.
    portfolio_id = Column(
        Integer,
        ForeignKey(
            "portfolios.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # =========================================================
    # SOURCE ACCOUNT
    # =========================================================

    # Account money/assets came FROM.
    source_account_id = Column(
        Integer,
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # =========================================================
    # DESTINATION ACCOUNT
    # =========================================================

    # Account money/assets went TO.
    destination_account_id = Column(
        Integer,
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    # =========================================================
    # ASSET
    # =========================================================

    # Investment/asset involved in the transaction.
    #
    # Nullable because many transactions do not involve an
    # investment asset.
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
    # SCHEDULED TRANSACTION
    # ============================================================

    # The scheduled action that generated this transaction,
    # when applicable.
    #
    # Nullable because most Transactions are created directly
    # rather than from a scheduled action.
    #
    # SET NULL preserves historical Transaction records if the
    # originating schedule is later deleted.
    scheduled_transaction_id = Column(
        Integer,
        ForeignKey(
            "scheduled_transactions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # =========================================================
    # TRANSACTION TYPE
    # =========================================================

    # Defines what financial event occurred.
    #
    # Stored as a string in PostgreSQL and controlled by the
    # TransactionType enum at the application layer.
    transaction_type = Column(
        String(30),
        nullable=False,
        index=True,
    )

    # =========================================================
    # STATUS
    # =========================================================

    # Execution state of the transaction.
    #
    # COMPLETED:
    #     Financial event successfully occurred.
    #
    # FAILED:
    #     Attempted but unsuccessful.
    #
    # CANCELLED:
    #     Cancelled before successful completion.
    #
    # All three statuses remain stored for audit/history.
    #
    # Financial calculation services must only treat
    # COMPLETED transactions as financially effective.
    status = Column(
        String(20),
        nullable=False,
        default=TransactionStatus.COMPLETED.value,
        server_default=TransactionStatus.COMPLETED.value,
        index=True,
    )

    # =========================================================
    # EXTERNAL REFERENCE
    # =========================================================

    # Reference supplied by an external financial provider.
    #
    # IMPORTANT:
    #
    # This is intentionally NOT unique.
    #
    # We have not established the correct uniqueness boundary
    # for external transaction references.
    #
    # It may eventually be scoped to:
    #
    #     provider + external_reference
    #     account + external_reference
    #     another provider-specific scope
    #
    # Therefore no database-level unique constraint is used.
    external_reference = Column(
        String(255),
        nullable=True,
        index=True,
    )

    # =========================================================
    # AMOUNT
    # =========================================================

    # Total monetary value of the transaction.
    amount = Column(
        Numeric(20, 8),
        nullable=False,
    )

    # =========================================================
    # CURRENCY
    # =========================================================

    # Currency of the monetary transaction amount.
    #
    # Stored as a string in PostgreSQL and validated at the
    # application layer.
    currency = Column(
        String(3),
        nullable=False,
    )

    # =========================================================
    # ASSET QUANTITY
    # =========================================================

    # Quantity of the asset involved in the transaction.
    quantity = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # =========================================================
    # UNIT
    # =========================================================

    # Unit corresponding to the asset quantity.
    unit = Column(
        String(30),
        nullable=True,
    )

    # =========================================================
    # UNIT PRICE
    # =========================================================

    # Price paid or received for one unit of an asset.
    unit_price = Column(
        Numeric(20, 8),
        nullable=True,
    )

    # =========================================================
    # MERCHANT / COUNTERPARTY
    # =========================================================

    # Merchant, exchange, counterparty, or external party.
    #
    # IMPORTANT:
    #
    # merchant is NOT the same architectural concept as an
    # external transaction provider.
    merchant = Column(
        String(255),
        nullable=True,
    )

    # =========================================================
    # DESCRIPTION
    # =========================================================

    # Additional human-readable information.
    description = Column(
        Text,
        nullable=True,
    )

    # =========================================================
    # TRANSACTION DATE
    # =========================================================

    # Date/time when the financial event actually occurred.
    #
    # IMPORTANT:
    #
    # Do NOT add index=True here.
    #
    # The dedicated database index created by the finalized
    # migration is:
    #
    #     ix_transactions_date
    #
    # Keeping index=True here would make SQLAlchemy/Alembic
    # expect another index named:
    #
    #     ix_transactions_transaction_date
    #
    # which is exactly the mismatch reported by alembic check.
    transaction_date = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    # =========================================================
    # RECORD TIMESTAMPS
    # =========================================================

    # When Finova recorded this transaction.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When this transaction record was last modified.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # Portfolio affected by this transaction.
    portfolio = relationship(
        "Portfolio",
        back_populates="transactions",
    )

    # Account money/assets came FROM.
    source_account = relationship(
        "Account",
        foreign_keys=[source_account_id],
        back_populates="source_transactions",
    )

    # Account money/assets went TO.
    destination_account = relationship(
        "Account",
        foreign_keys=[destination_account_id],
        back_populates="destination_transactions",
    )

    # Investment/asset involved.
    asset = relationship(
        "Asset",
        back_populates="transactions",
    )

    # Scheduled transaction that generated this transaction,
    # if applicable.
    scheduled_transaction = relationship(
        "ScheduledTransaction",
        back_populates="transactions",
    )