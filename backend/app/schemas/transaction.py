from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.app.models.transaction import (
    TransactionStatus,
    TransactionType,
)


class TransactionBase(BaseModel):
    """
    Shared validation and fields for Transaction schemas.

    A Transaction represents a financial event recorded by Finova.

    Financial consequences are determined by transaction status:

        COMPLETED:
            Financially effective.

        FAILED:
            Preserved for history/audit but not financially effective.

        CANCELLED:
            Preserved for history/audit but not financially effective.
    """

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    portfolio_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Portfolio affected by the transaction.",
    )

    source_account_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Account from which money/assets originated.",
    )

    destination_account_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Account to which money/assets were transferred.",
    )

    asset_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Asset involved in the transaction.",
    )

    # =========================================================
    # TRANSACTION CLASSIFICATION
    # =========================================================

    transaction_type: TransactionType = Field(
        description="Type of financial event.",
    )

    status: TransactionStatus = Field(
        default=TransactionStatus.COMPLETED,
        description="Execution status of the transaction.",
    )

    # =========================================================
    # EXTERNAL REFERENCE
    # =========================================================

    external_reference: Optional[str] = Field(
        default=None,
        max_length=255,
        description=(
            "Reference supplied by an external financial provider. "
            "Its uniqueness is provider-specific and is not enforced "
            "globally at this stage."
        ),
    )

    # =========================================================
    # MONETARY VALUE
    # =========================================================

    amount: Decimal = Field(
        gt=0,
        max_digits=20,
        decimal_places=8,
        description="Total monetary value of the transaction.",
    )

    currency: str = Field(
        description="ISO-style three-letter currency code.",
    )

    # =========================================================
    # ASSET QUANTITY
    # =========================================================

    quantity: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=8,
        description="Quantity of the asset involved.",
    )

    unit: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Unit corresponding to the asset quantity.",
    )

    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=8,
        description="Price paid or received for one unit of the asset.",
    )

    # =========================================================
    # MERCHANT / DESCRIPTION
    # =========================================================

    merchant: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Merchant, provider, exchange, or external party.",
    )

    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Human-readable description of the transaction.",
    )

    # =========================================================
    # TRANSACTION DATE
    # =========================================================

    transaction_date: datetime = Field(
        description="Date and time when the transaction occurred.",
    )

    # =========================================================
    # FIELD VALIDATORS
    # =========================================================

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """
        Normalize and validate currency codes.

        Whitespace is removed before validation so values such as
        " ngn " are correctly normalized to "NGN".
        """
        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "Currency must contain exactly three letters."
            )

        return value

    @field_validator(
        "external_reference",
        "unit",
        "merchant",
        "description",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """
        Normalize optional text fields.

        Empty/whitespace-only strings are converted to None.
        """
        if value is None:
            return None

        value = value.strip()

        return value or None

    # =========================================================
    # CROSS-FIELD VALIDATION
    # =========================================================

    @model_validator(mode="after")
    def validate_transaction_structure(self):
        """
        Validate relationships between transaction fields.

        BUY / SELL:
            Require asset, quantity, unit, and unit price.

        Quantity / unit:
            Must be supplied together.

        Unit price:
            Requires quantity.

        TRANSFER:
            Requires both source and destination accounts.
        """

        asset_transaction_types = {
            TransactionType.BUY,
            TransactionType.SELL,
        }

        # -----------------------------------------------------
        # BUY / SELL structure.
        # -----------------------------------------------------

        if self.transaction_type in asset_transaction_types:
            if self.asset_id is None:
                raise ValueError(
                    "asset_id is required for BUY and SELL transactions."
                )

            if self.quantity is None:
                raise ValueError(
                    "quantity is required for BUY and SELL transactions."
                )

            if self.unit_price is None:
                raise ValueError(
                    "unit_price is required for BUY and SELL transactions."
                )

            if self.unit is None:
                raise ValueError(
                    "unit is required for BUY and SELL transactions."
                )

        # -----------------------------------------------------
        # Quantity/unit consistency.
        # -----------------------------------------------------

        if self.quantity is not None and self.unit is None:
            raise ValueError(
                "unit is required when quantity is provided."
            )

        if self.unit is not None and self.quantity is None:
            raise ValueError(
                "quantity is required when unit is provided."
            )

        # -----------------------------------------------------
        # Unit price requires quantity.
        # -----------------------------------------------------

        if self.unit_price is not None and self.quantity is None:
            raise ValueError(
                "quantity is required when unit_price is provided."
            )

        # -----------------------------------------------------
        # TRANSFER structure.
        #
        # A transfer represents movement between two tracked
        # accounts, therefore both sides are required.
        # -----------------------------------------------------

        if self.transaction_type == TransactionType.TRANSFER:
            if (
                self.source_account_id is None
                or self.destination_account_id is None
            ):
                raise ValueError(
                    "TRANSFER transactions require both source "
                    "and destination accounts."
                )

        return self


class TransactionCreate(TransactionBase):
    """
    Schema used when creating a new Transaction.

    TransactionCreate inherits all shared transaction fields and
    validation rules from TransactionBase.

    Database-generated fields such as id and timestamps are excluded.
    """

    pass


class TransactionUpdate(BaseModel):
    """
    Schema used when updating an existing Transaction.

    Only explicitly supplied fields are modified.

    Historical financial records require special care. The
    service layer enforces which fields may actually be changed
    after a transaction becomes COMPLETED.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    portfolio_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    source_account_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    destination_account_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    asset_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    # =========================================================
    # TRANSACTION CLASSIFICATION
    # =========================================================

    transaction_type: Optional[TransactionType] = None

    status: Optional[TransactionStatus] = None

    # =========================================================
    # EXTERNAL REFERENCE
    # =========================================================

    external_reference: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    # =========================================================
    # MONETARY VALUE
    # =========================================================

    amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=8,
    )

    currency: Optional[str] = Field(
        default=None,
    )

    # =========================================================
    # ASSET QUANTITY
    # =========================================================

    quantity: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=8,
    )

    unit: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=8,
    )

    # =========================================================
    # MERCHANT / DESCRIPTION
    # =========================================================

    merchant: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    # =========================================================
    # TRANSACTION DATE
    # =========================================================

    transaction_date: Optional[datetime] = None

    # =========================================================
    # FIELD VALIDATORS
    # =========================================================

    @field_validator("currency")
    @classmethod
    def validate_currency(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """
        Normalize and validate an optional currency code.

        Whitespace is removed before validation so values such as
        " ngn " are correctly normalized to "NGN".
        """
        if value is None:
            return None

        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "Currency must contain exactly three letters."
            )

        return value

    @field_validator(
        "external_reference",
        "unit",
        "merchant",
        "description",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """
        Normalize optional text fields.

        Empty/whitespace-only strings are converted to None.
        """
        if value is None:
            return None

        value = value.strip()

        return value or None


class TransactionResponse(TransactionBase):
    """
    Schema returned by the API when exposing a Transaction.

    Response validation reuses TransactionBase so the API representation
    follows the same field and structural rules as transaction creation.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(
        gt=0,
    )

    created_at: datetime

    updated_at: datetime