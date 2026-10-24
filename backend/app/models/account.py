import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.connection import Base


class AccountType(str, enum.Enum):
    """
    Supported financial account types in Finova.

    The enum provides a controlled set of account categories
    that is shared between the database model and API schema.
    """

    BANK = "bank"
    MOBILE_MONEY = "mobile_money"
    CASH = "cash"
    BROKERAGE = "brokerage"
    CRYPTO_EXCHANGE = "crypto_exchange"
    CRYPTO_WALLET = "crypto_wallet"


class Account(Base):
    """
    Represents a financial account, wallet, or money container
    owned by a Finova user.

    Examples:
        - Bank account
        - Mobile money account
        - Cash wallet
        - Brokerage account
        - Crypto exchange account
        - Crypto wallet

    An Account represents WHERE funds are held.

    It does NOT represent:
        - an investment asset
        - a portfolio
        - a holding
        - historical acquisition cost

    Those concepts are represented by their respective models.

    Account balances represent the latest known balance in the
    account's native currency or denomination.

    A balance may be positive, zero, or negative. A negative
    balance can represent a legitimate financial position such
    as an overdraft or negative cash position. The financial
    health / net-worth layer determines how such balances
    contribute to the user's overall financial position.

    External synchronization fields are system-controlled.
    User-facing account operations must not directly manipulate
    connection state.
    """

    __tablename__ = "accounts"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # OWNER
    # =========================================================

    # Every account belongs to exactly one user.
    #
    # RESTRICT prevents a User row from being deleted while
    # financial accounts still reference it.
    #
    # Finova uses account deactivation rather than ordinary
    # hard deletion, so this provides database-level protection
    # against accidental user deletion.
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # =========================================================
    # ACCOUNT INFORMATION
    # =========================================================

    # User-defined name for the account.
    #
    # Examples:
    #     Main Bank Account
    #     Binance Wallet
    #     Emergency Cash
    name = Column(
        String(150),
        nullable=False,
    )

    # Controlled account category.
    #
    # native_enum=False keeps this represented as a string in
    # PostgreSQL while SQLAlchemy still validates it against the
    # Python enum.
    account_type = Column(
        Enum(
            AccountType,
            name="account_type_enum",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )

    # Financial institution, exchange, or other provider name.
    #
    # Examples:
    #     GTBank
    #     Access Bank
    #     Binance
    institution_name = Column(
        String(150),
        nullable=True,
    )

    # Native currency or denomination of the account.
    #
    # Examples:
    #     NGN
    #     USD
    #     EUR
    #     BTC
    #     ETH
    #
    # This remains a String rather than an enum because the
    # supported denomination set can grow over time.
    currency = Column(
        String(10),
        nullable=False,
    )

    # =========================================================
    # BALANCE
    # =========================================================

    # Latest known balance in the account's native currency or
    # denomination.
    #
    # Numeric is used instead of Float because financial values
    # require exact decimal representation.
    #
    # Negative balances are intentionally permitted. Examples
    # include legitimate bank overdrafts or other negative
    # account positions.
    balance = Column(
        Numeric(30, 18),
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # =========================================================
    # EXTERNAL CONNECTION
    # =========================================================

    # Indicates whether Finova currently has an active external
    # connection for this account.
    #
    # False means the account may be maintained manually.
    is_connected = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    # External financial-data provider.
    #
    # Examples:
    #     mono
    #     providus
    #     binance
    #
    # This identifies the provider, not the user's secret
    # credentials.
    provider = Column(
        String(50),
        nullable=True,
    )

    # Identifier assigned by the external provider.
    #
    # This is NOT:
    #     - an API key
    #     - a password
    #     - an access token
    #     - a secret
    external_account_id = Column(
        String(255),
        nullable=True,
    )

    # =========================================================
    # ACCOUNT STATUS
    # =========================================================

    # Accounts are normally deactivated rather than deleted so
    # financial history remains available.
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    # =========================================================
    # SYNCHRONIZATION
    # =========================================================

    # Last time Finova successfully refreshed the account's
    # external information or balance.
    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # ---------------------------------------------------------
    # USER
    # ---------------------------------------------------------

    user = relationship(
        "User",
        back_populates="accounts",
    )

    # ---------------------------------------------------------
    # TRANSACTIONS
    # ---------------------------------------------------------

    # Transactions where this account is the source.
    source_transactions = relationship(
        "Transaction",
        foreign_keys="Transaction.source_account_id",
        back_populates="source_account",
    )

    # Transactions where this account is the destination.
    destination_transactions = relationship(
        "Transaction",
        foreign_keys="Transaction.destination_account_id",
        back_populates="destination_account",
    )

    # ---------------------------------------------------------
    # SCHEDULED TRANSACTIONS
    # ---------------------------------------------------------

    # Scheduled transactions where this account is the source.
    scheduled_source_transactions = relationship(
        "ScheduledTransaction",
        foreign_keys="ScheduledTransaction.source_account_id",
        back_populates="source_account",
    )

    # Scheduled transactions where this account is the destination.
    scheduled_destination_transactions = relationship(
        "ScheduledTransaction",
        foreign_keys="ScheduledTransaction.destination_account_id",
        back_populates="destination_account",
    )

    # =========================================================
    # DATABASE CONSTRAINTS / INDEXES
    # =========================================================

    __table_args__ = (
        # -----------------------------------------------------
        # Currency format
        # -----------------------------------------------------
        #
        # Finova currently accepts uppercase alphanumeric
        # currency/denomination identifiers between 3 and 10
        # characters.
        #
        # Examples:
        #     NGN
        #     USD
        #     BTC
        #     USDT
        #
        # This validates the basic format only. It does not
        # attempt to maintain a hard-coded list of every
        # supported currency or crypto asset.
        CheckConstraint(
            "currency ~ '^[A-Z0-9]{3,10}$'",
            name="ck_accounts_currency_format",
        ),

        # -----------------------------------------------------
        # User + active status
        # -----------------------------------------------------
        #
        # Efficiently retrieves a user's active accounts.
        Index(
            "ix_accounts_user_active",
            "user_id",
            "is_active",
        ),

        # -----------------------------------------------------
        # User + account type
        # -----------------------------------------------------
        #
        # Useful for queries such as:
        #     all brokerage accounts for a user
        #     all bank accounts for a user
        Index(
            "ix_accounts_user_type",
            "user_id",
            "account_type",
        ),

        # -----------------------------------------------------
        # External account lookup
        # -----------------------------------------------------
        Index(
            "ix_accounts_external_account_id",
            "external_account_id",
        ),

        # -----------------------------------------------------
        # Connected external account uniqueness
        # -----------------------------------------------------
        #
        # The same provider account must not be linked to
        # multiple active connected Account records.
        #
        # PostgreSQL's partial unique index means this rule only
        # applies when is_connected = true.
        #
        # Manually maintained accounts therefore remain free to
        # have NULL provider/external identifiers.
        Index(
            "uq_accounts_provider_external_id_connected",
            "provider",
            "external_account_id",
            unique=True,
            postgresql_where=text(
                "is_connected = true"
            ),
        ),
    )