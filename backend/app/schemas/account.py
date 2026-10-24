import enum
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class AccountType(str, enum.Enum):
    """
    Mirrors app.models.account.AccountType.

    These values must remain synchronized with the SQLAlchemy
    AccountType enum used by the Account model.
    """

    BANK = "bank"
    MOBILE_MONEY = "mobile_money"
    CASH = "cash"
    BROKERAGE = "brokerage"
    CRYPTO_EXCHANGE = "crypto_exchange"
    CRYPTO_WALLET = "crypto_wallet"


def _validate_currency(value: str) -> str:
    """
    Normalize and validate an account currency/denomination.

    Examples:
        NGN
        USD
        EUR
        BTC
        USDT
    """

    value = value.strip().upper()

    if not (3 <= len(value) <= 10):
        raise ValueError(
            "Currency must be 3-10 alphanumeric characters."
        )

    if not value.isalnum():
        raise ValueError(
            "Currency must contain only letters and numbers."
        )

    return value


class AccountBase(BaseModel):
    """
    Shared fields for Account API schemas.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="User-defined name for the account.",
    )

    account_type: AccountType = Field(
        ...,
        description="Type of financial account.",
    )

    institution_name: str | None = Field(
        default=None,
        max_length=150,
        description="Financial institution or provider name.",
    )

    currency: str = Field(
        ...,
        min_length=3,
        max_length=10,
        description=(
            "Account currency or denomination "
            "(e.g. NGN, USD, BTC)."
        ),
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return _validate_currency(value)


class AccountCreate(AccountBase):
    """
    Schema used when creating an Account.

    Ownership is determined by the authenticated user and is
    therefore never accepted from the client.

    External connection fields are also excluded. A normal
    user-created account begins as a manually maintained,
    disconnected account.
    """

    balance: Decimal = Field(
        default=Decimal("0"),
        description=(
            "Initial account balance. Negative values are "
            "allowed to represent overdrafts or other "
            "legitimate negative balances."
        ),
    )


class AccountUpdate(BaseModel):
    """
    User-facing schema for partially updating an Account.

    External connection fields are deliberately excluded because
    they are controlled by trusted synchronization infrastructure.

    All fields are optional so PATCH-style updates are supported.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    account_type: AccountType | None = None

    institution_name: str | None = Field(
        default=None,
        max_length=150,
    )

    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
    )

    balance: Decimal | None = None

    is_active: bool | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _validate_currency(value)


class AccountSyncUpdate(BaseModel):
    """
    Internal schema used by trusted synchronization
    infrastructure.

    This schema must NOT be exposed directly through a normal
    user-facing account update endpoint.

    It is intended for trusted backend processes that synchronize
    account information from an external provider.
    """

    balance: Decimal | None = None

    is_connected: bool | None = None

    provider: str | None = Field(
        default=None,
        max_length=50,
    )

    external_account_id: str | None = Field(
        default=None,
        max_length=255,
    )

    last_synced_at: datetime | None = None


class AccountResponse(AccountBase):
    """
    Safe Account representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    user_id: int

    balance: Decimal

    is_connected: bool

    provider: str | None

    external_account_id: str | None

    is_active: bool

    last_synced_at: datetime | None

    created_at: datetime

    updated_at: datetime