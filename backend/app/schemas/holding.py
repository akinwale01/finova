from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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


class ValuationMethod(str, Enum):
    """How Finova obtains a holding's current valuation."""

    MARKET_PRICE = "MARKET_PRICE"
    USER_VALUED = "USER_VALUED"


# ============================================================
# SHARED VALIDATION
# ============================================================


def normalize_currency(value: object) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        # Pydantic validators use ValueError to produce structured ValidationError.
        raise ValueError("Currency must be a string.")  # noqa: TRY004

    value = value.strip().upper()

    if len(value) != 3 or not value.isalpha():
        raise ValueError("Currency must be a three-letter currency code.")

    return value


class HoldingBase(BaseModel):
    """Common fields used when establishing a holding position."""

    model_config = ConfigDict(extra="forbid")

    quantity: Decimal = Field(
        ...,
        gt=0,
        max_digits=20,
        decimal_places=8,
        description=(
            "Current quantity, expressed in the canonical unit "
            "defined by the associated Asset."
        ),
    )

    ownership_percentage: Decimal | None = Field(
        default=None,
        max_digits=7,
        decimal_places=4,
        ge=0,
        le=100,
        description="Ownership percentage for applicable assets.",
    )

    valuation_method: ValuationMethod = Field(
        ...,
        description="Method used to obtain the current valuation.",
    )

    current_unit_price: Decimal | None = Field(
        default=None,
        max_digits=20,
        decimal_places=8,
        ge=0,
    )

    current_total_value: Decimal | None = Field(
        default=None,
        max_digits=20,
        decimal_places=8,
        ge=0,
    )

    valuation_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    @field_validator("valuation_currency", mode="before")
    @classmethod
    def validate_valuation_currency(cls, value: object) -> str | None:
        return normalize_currency(value)

    @model_validator(mode="after")
    def validate_valuation(self):
        """Require currency whenever a valuation amount is supplied."""

        has_valuation = (
            self.current_unit_price is not None
            or self.current_total_value is not None
        )

        if has_valuation and self.valuation_currency is None:
            raise ValueError(
                "valuation_currency is required when a valuation is supplied."
            )

        if (
            self.current_unit_price is not None
            and self.current_total_value is not None
        ):
            expected_total = self.quantity * self.current_unit_price

            if self.current_total_value != expected_total:
                raise ValueError(
                    "current_total_value must equal quantity multiplied "
                    "by current_unit_price."
                )

        return self


# ============================================================
# CREATE
# ============================================================


class HoldingCreate(HoldingBase):
    """
    Schema for an internally controlled holding-creation workflow.

    This is intended for transaction processing, opening balances,
    or imports—not unrestricted ordinary CRUD creation.
    """

    portfolio_id: int = Field(..., gt=0)
    asset_id: int = Field(..., gt=0)

    total_cost_basis: Decimal = Field(
        ...,
        ge=0,
        max_digits=20,
        decimal_places=8,
    )

    cost_basis_per_unit: Decimal = Field(
        ...,
        ge=0,
        max_digits=20,
        decimal_places=8,
    )

    cost_basis_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
    )

    @field_validator("cost_basis_currency", mode="before")
    @classmethod
    def validate_cost_basis_currency(cls, value: object) -> str:
        normalized = normalize_currency(value)

        if normalized is None:
            raise ValueError("cost_basis_currency is required.")

        return normalized

    @model_validator(mode="after")
    def validate_cost_basis(self):
        expected_per_unit = (
            self.total_cost_basis / self.quantity
        ).quantize(
            Decimal("0.00000001"),
            rounding=ROUND_HALF_UP,
        )

        if self.cost_basis_per_unit != expected_per_unit:
            raise ValueError(
                "cost_basis_per_unit must equal total_cost_basis "
                "divided by quantity, rounded to 8 decimal places."
            )

        return self


# ============================================================
# CONTROLLED OWNERSHIP UPDATE
# ============================================================


class HoldingUpdate(BaseModel):
    """
    Controlled update for ownership percentage only.

    Quantity, asset identity, portfolio identity, cost basis,
    and valuation are deliberately excluded.

    An explicit null can clear an existing ownership percentage.
    An empty payload is rejected.
    """

    model_config = ConfigDict(extra="forbid")

    ownership_percentage: Decimal | None = Field(
        default=None,
        max_digits=7,
        decimal_places=4,
        ge=0,
        le=100,
    )

    @model_validator(mode="after")
    def require_ownership_change(self):
        if "ownership_percentage" not in self.model_fields_set:
            raise ValueError(
                "Provide ownership_percentage to update the holding."
            )

        return self


# ============================================================
# MANUAL VALUATION UPDATE
# ============================================================


class HoldingValuationUpdate(BaseModel):
    """
    Update the current manual valuation of an existing holding.

    Does not permit changes to quantity, ownership, cost basis,
    asset identity, portfolio identity, or valuation method.

    The service determines the method as USER_VALUED.
    """

    model_config = ConfigDict(extra="forbid")

    current_unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=8,
    )

    current_total_value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=20,
        decimal_places=8,
    )

    valuation_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    @field_validator("valuation_currency", mode="before")
    @classmethod
    def validate_valuation_currency(cls, value: object) -> str | None:
        return normalize_currency(value)

    @model_validator(mode="after")
    def validate_valuation_update(self):
        has_unit_price = self.current_unit_price is not None
        has_total_value = self.current_total_value is not None

        # An actual valuation amount must be supplied.
        if not has_unit_price and not has_total_value:
            raise ValueError(
                "Provide either current_unit_price or current_total_value."
            )

        # Every valuation must identify its currency.
        if self.valuation_currency is None:
            raise ValueError(
                "valuation_currency is required when providing a valuation."
            )

        return self


# ============================================================
# READ / RESPONSE
# ============================================================


class HoldingRead(BaseModel):
    """Public API representation of a holding."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    asset_id: int

    # Quantity is always expressed in Asset.unit.
    quantity: Decimal

    ownership_percentage: Decimal | None

    valuation_method: ValuationMethod
    current_unit_price: Decimal | None
    current_total_value: Decimal | None
    valuation_currency: str | None
    price_updated_at: datetime | None

    total_cost_basis: Decimal
    cost_basis_per_unit: Decimal
    cost_basis_currency: str

    created_at: datetime
    updated_at: datetime


# ============================================================
# LIST RESPONSE
# ============================================================


class HoldingListResponse(BaseModel):
    """Standard paginated/list response for holdings."""

    items: list[HoldingRead]
    total: int = Field(..., ge=0)