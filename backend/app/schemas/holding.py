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


class ValuationMethod(str, Enum):
    """
    Defines how Finova determines the current valuation
    of a holding.
    """

    MARKET_PRICE = "market_price"
    USER_VALUED = "user_valued"
    CALCULATED = "calculated"


# ============================================================
# SHARED VALIDATION
# ============================================================


class HoldingBase(BaseModel):
    """
    Fields shared by Holding creation and valuation-related
    operations.

    Historical acquisition data remains separate from current
    valuation data.
    """

    quantity: Decimal = Field(
        ...,
        max_digits=20,
        decimal_places=8,
        ge=0,
        description="Current quantity of the asset owned.",
    )

    unit: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unit used to describe the quantity.",
    )

    ownership_percentage: Decimal | None = Field(
        default=None,
        max_digits=7,
        decimal_places=4,
        ge=0,
        le=100,
        description="Ownership percentage for ownership-based assets.",
    )

    valuation_method: ValuationMethod = Field(
        ...,
        description="Method used to determine the current valuation.",
    )

    current_unit_price: Decimal | None = Field(
        default=None,
        max_digits=20,
        decimal_places=8,
        ge=0,
        description="Current value of one unit of the asset.",
    )

    current_total_value: Decimal | None = Field(
        default=None,
        max_digits=20,
        decimal_places=8,
        ge=0,
        description="Current total value of the holding.",
    )

    valuation_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Currency in which the current valuation is expressed.",
    )

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """
        Normalize the quantity unit while rejecting blank values.
        """

        value = value.strip()

        if not value:
            raise ValueError("unit must not be blank")

        return value

    @field_validator("valuation_currency", mode="before")
    @classmethod
    def validate_valuation_currency(
        cls,
        value: object,
    ) -> str | None:
        """
        Normalize and validate valuation currency before Pydantic
        applies the exact three-character length constraints.
        """

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                "valuation_currency must be a string"
            )

        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "valuation_currency must be a valid 3-letter currency code"
            )

        return value

    @model_validator(mode="after")
    def validate_valuation(self):
        """
        Ensure valuation fields remain internally consistent.

        A holding may exist before a current market valuation is
        available.

        However, whenever a current unit price or total value is
        provided, a valuation currency must also be provided.
        """

        if (
            self.current_unit_price is not None
            and self.valuation_currency is None
        ):
            raise ValueError(
                "valuation_currency is required when "
                "current_unit_price is provided"
            )

        if (
            self.current_total_value is not None
            and self.valuation_currency is None
        ):
            raise ValueError(
                "valuation_currency is required when "
                "current_total_value is provided"
            )

        return self


# ============================================================
# CREATE
# ============================================================


class HoldingCreate(HoldingBase):
    """
    Schema used when creating a new Holding.

    Historical acquisition information is stored separately from
    current/live valuation information.
    """

    portfolio_id: int = Field(
        ...,
        gt=0,
        description="Portfolio that owns the holding.",
    )

    asset_id: int = Field(
        ...,
        gt=0,
        description="Asset represented by the holding.",
    )

    total_cost_basis: Decimal = Field(
        ...,
        max_digits=20,
        decimal_places=8,
        ge=0,
        description="Total historical acquisition cost.",
    )

    cost_basis_per_unit: Decimal = Field(
        ...,
        max_digits=20,
        decimal_places=8,
        ge=0,
        description="Historical acquisition cost per unit.",
    )

    cost_basis_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Currency used for historical cost basis.",
    )

    @field_validator("cost_basis_currency", mode="before")
    @classmethod
    def validate_cost_basis_currency(cls, value: Any) -> str:
        """
        Normalize and validate cost-basis currency before Pydantic
        applies the exact three-character length constraints.
        """

        if not isinstance(value, str):
            raise TypeError("cost_basis_currency must be a string")

        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "cost_basis_currency must be a valid 3-letter currency code"
            )

        return value


# ============================================================
# UPDATE
# ============================================================


class HoldingUpdate(BaseModel):
    """
    Schema used to update an existing Holding.

    Historical cost-basis fields are deliberately excluded.

    A normal holding update must never overwrite historical
    acquisition information simply because market valuation
    changes.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    quantity: Decimal | None = Field(
        default=None,
        max_digits=20,
        decimal_places=8,
        ge=0,
    )

    unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    ownership_percentage: Decimal | None = Field(
        default=None,
        max_digits=7,
        decimal_places=4,
        ge=0,
        le=100,
    )

    valuation_method: ValuationMethod | None = None

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

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str | None) -> str | None:
        """
        Normalize the unit when supplied.
        """

        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("unit must not be blank")

        return value

    @field_validator("valuation_currency", mode="before")
    @classmethod
    def validate_valuation_currency(
        cls,
        value: object | None,
    ) -> str | None:
        """
        Normalize and validate valuation currency before Pydantic
        applies the exact three-character length constraints.
        """

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                "valuation_currency must be a string"
            )

        value = value.strip().upper()

        if len(value) != 3 or not value.isalpha():
            raise ValueError(
                "valuation_currency must be a valid 3-letter currency code"
            )

        return value


# ============================================================
# READ / RESPONSE
# ============================================================


class HoldingRead(BaseModel):
    """
    Public API representation of a Holding.

    Contains both historical acquisition information and current
    valuation information.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    portfolio_id: int

    asset_id: int

    quantity: Decimal

    unit: str

    ownership_percentage: Decimal | None

    valuation_method: ValuationMethod

    current_unit_price: Decimal | None

    current_total_value: Decimal | None

    price_updated_at: datetime | None

    total_cost_basis: Decimal

    cost_basis_per_unit: Decimal

    cost_basis_currency: str

    valuation_currency: str | None

    created_at: datetime

    updated_at: datetime


# ============================================================
# LIST RESPONSE
# ============================================================


class HoldingListResponse(BaseModel):
    """
    Standard collection response for holdings.
    """

    items: list[HoldingRead]

    total: int = Field(
        ...,
        ge=0,
    )