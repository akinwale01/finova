from datetime import datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =========================================================
# SUPPORTED ASSET VALUES
# =========================================================

ASSET_TYPES = {
    "STOCK",
    "ETF",
    "CRYPTO",
    "FOREX",
    "COMMODITY",
    "REAL_ESTATE",
    "BUSINESS",
    "PRECIOUS_METAL",
    "COLLECTIBLE",
    "CASH",
    "OTHER",
}

VALUATION_METHODS = {
    "MARKET",
    "MANUAL",
}

UNITS = {
    "SHARE",
    "COIN",
    "UNIT",
    "OUNCE",
    "GRAM",
    "CURRENCY",
    "SQ_METER",
}


# =========================================================
# VALIDATION HELPERS
# =========================================================

def _normalize_currency(value: str) -> str:
    """
    Normalize and validate a pricing currency.

    Examples:
        usd -> USD
        ngn -> NGN
        btc -> BTC
    """

    value = value.strip().upper()

    if not (3 <= len(value) <= 10):
        raise ValueError(
            "Currency must be between 3 and 10 characters."
        )

    if not value.isalnum():
        raise ValueError(
            "Currency must contain only letters and numbers."
        )

    return value


def _normalize_symbol(value: str | None) -> str | None:
    """
    Normalize an asset symbol.

    Symbols are stored consistently in uppercase.

    Examples:
        aapl -> AAPL
        btc -> BTC
    """

    if value is None:
        return None

    value = value.strip().upper()

    return value or None


def _normalize_name(value: str) -> str:
    """
    Normalize a human-readable asset name.

    Only surrounding whitespace is removed.
    Internal capitalization is preserved.
    """

    value = value.strip()

    if not value:
        raise ValueError("Asset name cannot be empty.")

    return value


def _normalize_market(value: str | None) -> str | None:
    """
    Normalize an exchange/market name.

    We preserve the supplied capitalization because market names
    are human-readable/external identifiers rather than controlled
    enum values.
    """

    if value is None:
        return None

    value = value.strip()

    return value or None


def _normalize_asset_type(value: str) -> str:
    """
    Normalize and validate the asset category.
    """

    value = value.strip().upper()

    if value not in ASSET_TYPES:
        raise ValueError(
            "Invalid asset type. "
            f"Supported values: {', '.join(sorted(ASSET_TYPES))}."
        )

    return value


def _normalize_valuation_method(value: str) -> str:
    """
    Normalize and validate the valuation method.
    """

    value = value.strip().upper()

    if value not in VALUATION_METHODS:
        raise ValueError(
            "Invalid valuation method. "
            f"Supported values: "
            f"{', '.join(sorted(VALUATION_METHODS))}."
        )

    return value


def _normalize_unit(value: str) -> str:
    """
    Normalize and validate the asset unit.
    """

    value = value.strip().upper()

    if value not in UNITS:
        raise ValueError(
            "Invalid asset unit. "
            f"Supported values: {', '.join(sorted(UNITS))}."
        )

    return value


# =========================================================
# ASSET BASE
# =========================================================

class AssetBase(BaseModel):
    """
    Shared fields for AssetCreate and AssetUpdate.

    AssetBase describes the identity and valuation configuration
    of an asset.

    It intentionally does NOT contain:

        - ownership
        - quantity
        - purchase price
        - cost basis
        - current market price
        - current market value
        - unrealized P/L

    Those belong to Holding, Transaction, and the valuation/
    market-data layers.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Human-readable canonical asset name.",
        examples=[
            "Apple Inc.",
            "Bitcoin",
            "Physical Gold",
        ],
    )

    symbol: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Canonical asset symbol where applicable, "
            "such as AAPL, BTC, or EUR/USD."
        ),
        examples=[
            "AAPL",
            "BTC",
            "EUR/USD",
        ],
    )

    asset_type: str = Field(
        ...,
        max_length=30,
        description="Broad category of the asset.",
        examples=[
            "STOCK",
            "CRYPTO",
            "REAL_ESTATE",
        ],
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional additional information about the asset.",
    )

    market: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Exchange or market where the asset is traded."
        ),
        examples=[
            "NASDAQ",
            "NYSE",
            "LSE",
            "Binance",
        ],
    )

    is_market_backed: bool = Field(
        default=False,
        description=(
            "Whether the asset obtains its valuation from "
            "market-data infrastructure."
        ),
    )

    valuation_method: str = Field(
        default="MANUAL",
        max_length=30,
        description=(
            "How Finova obtains the asset's current valuation."
        ),
    )

    pricing_currency: str = Field(
        ...,
        min_length=3,
        max_length=10,
        description=(
            "Currency in which the asset price/value is expressed."
        ),
        examples=[
            "USD",
            "NGN",
            "EUR",
        ],
    )

    unit: str = Field(
        default="UNIT",
        max_length=30,
        description=(
            "Unit represented by one quantity of the asset."
        ),
        examples=[
            "SHARE",
            "COIN",
            "UNIT",
            "OUNCE",
            "GRAM",
            "CURRENCY",
            "SQ_METER",
        ],
    )

    # =========================================================
    # FIELD VALIDATORS
    # =========================================================

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_name(value)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_symbol(value)

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, value: str) -> str:
        return _normalize_asset_type(value)

    @field_validator("market")
    @classmethod
    def validate_market(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_market(value)

    @field_validator("valuation_method")
    @classmethod
    def validate_valuation_method(cls, value: str) -> str:
        return _normalize_valuation_method(value)

    @field_validator("pricing_currency")
    @classmethod
    def validate_pricing_currency(cls, value: str) -> str:
        return _normalize_currency(value)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        return _normalize_unit(value)

    # =========================================================
    # CROSS-FIELD VALIDATION
    # =========================================================

    @model_validator(mode="after")
    def validate_valuation_configuration(self):
        """
        Keep the API representation consistent with the
        database CHECK constraint:

            is_market_backed = true
                -> valuation_method = MARKET

            is_market_backed = false
                -> valuation_method = MANUAL
        """

        if self.is_market_backed and self.valuation_method != "MARKET":
            raise ValueError(
                "Market-backed assets must use MARKET valuation."
            )

        if not self.is_market_backed and self.valuation_method != "MANUAL":
            raise ValueError(
                "Non-market assets must use MANUAL valuation."
            )

        return self


# =========================================================
# ASSET CREATE
# =========================================================

class AssetCreate(AssetBase):
    """
    Schema used when creating an asset.

    Provider integration fields are deliberately excluded.

    Normal users may describe the asset and its valuation
    configuration, but they must not arbitrarily assign Finova's
    internal market-data provider mapping.
    """

    pass


# =========================================================
# ASSET UPDATE
# =========================================================

class AssetUpdate(BaseModel):
    """
    User-facing schema for partially updating an existing asset.

    Provider integration fields are intentionally excluded.

    All fields are optional so PATCH-style updates are supported.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    symbol: str | None = Field(
        default=None,
        max_length=50,
    )

    asset_type: str | None = Field(
        default=None,
        max_length=30,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    market: str | None = Field(
        default=None,
        max_length=100,
    )

    is_market_backed: bool | None = None

    valuation_method: str | None = Field(
        default=None,
        max_length=30,
    )

    pricing_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
    )

    unit: str | None = Field(
        default=None,
        max_length=30,
    )

    is_active: bool | None = None

    # =========================================================
    # FIELD VALIDATORS
    # =========================================================

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _normalize_name(value)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_symbol(value)

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _normalize_asset_type(value)

    @field_validator("market")
    @classmethod
    def validate_market(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_market(value)

    @field_validator("valuation_method")
    @classmethod
    def validate_valuation_method(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _normalize_valuation_method(value)

    @field_validator("pricing_currency")
    @classmethod
    def validate_pricing_currency(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _normalize_currency(value)

    @field_validator("unit")
    @classmethod
    def validate_unit(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return _normalize_unit(value)

    # =========================================================
    # CROSS-FIELD VALIDATION
    # =========================================================

    @model_validator(mode="after")
    def validate_partial_valuation_configuration(self):
        """
        Validates valuation configuration when both related
        fields are supplied in the same update.

        The service layer must validate the final merged state
        when only one of these fields is changed.
        """

        if (
            self.is_market_backed is not None
            and self.valuation_method is not None
        ):
            if (
                self.is_market_backed
                and self.valuation_method != "MARKET"
            ):
                raise ValueError(
                    "Market-backed assets must use MARKET valuation."
                )

            if (
                not self.is_market_backed
                and self.valuation_method != "MANUAL"
            ):
                raise ValueError(
                    "Non-market assets must use MANUAL valuation."
                )

        return self


# =========================================================
# ASSET RESPONSE
# =========================================================

class AssetResponse(AssetBase):
    """
    Public API representation of an asset.

    Provider integration metadata is returned for read operations,
    but is not accepted through AssetCreate or AssetUpdate.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    market_data_provider: str | None

    external_asset_id: str | None

    is_active: bool

    created_at: datetime

    updated_at: datetime


# =========================================================
# ASSET LIST RESPONSE
# =========================================================

class AssetListResponse(BaseModel):
    """
    Standard response wrapper for multiple assets.

    Keeping a wrapper gives Finova room to add pagination and
    filtering metadata without breaking the API contract.
    """

    items: list[AssetResponse]

    total: int