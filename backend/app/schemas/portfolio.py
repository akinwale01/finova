from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =========================================================
# PORTFOLIO CREATE
# =========================================================


class PortfolioCreate(BaseModel):
    """
    Data required to create a new portfolio.

    The authenticated user is determined by the application
    layer, so user_id is intentionally not accepted here.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User-defined name of the portfolio.",
        examples=["Long-Term Investments"],
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """
        Normalize portfolio names before they reach the
        service/model layer.

        Leading and trailing whitespace is removed so values
        such as:

            " Crypto Portfolio"
            "Crypto Portfolio "

        are stored consistently.
        """

        value = value.strip()

        if not value:
            raise ValueError("Portfolio name cannot be empty.")

        return value


# =========================================================
# PORTFOLIO UPDATE
# =========================================================


class PortfolioUpdate(BaseModel):
    """
    Data that may be changed on an existing portfolio.

    All fields are optional so this schema supports partial
    updates.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New name for the portfolio.",
        examples=["Crypto Portfolio"],
    )

    is_active: bool | None = Field(
        default=None,
        description="Whether the portfolio is active.",
    )

    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize the portfolio name when one is supplied.

        None is preserved because the field is optional and
        omitted fields must remain unchanged during partial
        updates.
        """

        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Portfolio name cannot be empty.")

        return value


# =========================================================
# PORTFOLIO RESPONSE
# =========================================================


class PortfolioResponse(BaseModel):
    """
    Public API representation of a portfolio.

    Database-owned fields such as id and timestamps are
    returned by the API but cannot be supplied by clients
    through PortfolioCreate or PortfolioUpdate.
    """

    id: int
    user_id: int
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# =========================================================
# PORTFOLIO LIST RESPONSE
# =========================================================


class PortfolioListResponse(BaseModel):
    """
    Standard response wrapper for returning multiple
    portfolios.

    This provides a stable response structure for list
    endpoints and leaves room for pagination metadata without
    changing the individual portfolio response schema.
    """

    items: list[PortfolioResponse]
    total: int