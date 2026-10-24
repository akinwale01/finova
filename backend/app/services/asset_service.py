from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions.common import (
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetUpdate
from app.services.base_service import BaseService


class AssetService(BaseService[Asset]):
    """
    Business-logic layer for canonical Finova assets.

    Assets are global canonical definitions. They are not owned by
    individual users.

    Asset:
        Describes WHAT the financial asset is.

    Holding:
        Describes HOW MUCH of that asset a user owns.

    Transaction:
        Describes HOW that asset was acquired, disposed of,
        transferred, or otherwise transacted.

    This service therefore does NOT manage:
        - user ownership
        - quantities
        - purchase prices
        - cost basis
        - current market prices
        - current market value
        - unrealized P/L
        - holdings
        - transactions
        - provider credentials

    Provider mapping fields are also deliberately excluded from
    normal user-facing create/update operations.
    """

    model = Asset

    def __init__(self, db: Session):
        super().__init__(db)

    # ================================================================
    # RETRIEVAL
    # ================================================================

    def get_asset(
        self,
        asset_id: int,
        *,
        active_only: bool = False,
    ) -> Asset | None:
        """
        Retrieve an asset by ID.

        Assets are global, so no user ownership filtering is used.
        """
        query = self.db.query(self.model).filter(
            self.model.id == asset_id,
        )

        if active_only:
            query = query.filter(
                self.model.is_active.is_(True),
            )

        return query.first()

    def require_asset(
        self,
        asset_id: int,
        *,
        active_only: bool = False,
    ) -> Asset:
        """
        Retrieve an asset or raise NotFoundError.
        """
        asset = self.get_asset(
            asset_id=asset_id,
            active_only=active_only,
        )

        if asset is None:
            raise NotFoundError("Asset not found.")

        return asset

    def list_assets(
        self,
        *,
        active_only: bool = True,
        asset_type: str | None = None,
    ) -> list[Asset]:
        """
        Return canonical assets.

        By default only active assets are returned.

        Results are deterministic and ordered by name and ID.
        """
        query = self.db.query(self.model)

        if active_only:
            query = query.filter(
                self.model.is_active.is_(True),
            )

        if asset_type is not None:
            asset_type = asset_type.strip().upper()

            query = query.filter(
                self.model.asset_type == asset_type,
            )

        return (
            query
            .order_by(
                self.model.name.asc(),
                self.model.id.asc(),
            )
            .all()
        )

    def get_assets_by_type(
        self,
        asset_type: str,
        *,
        active_only: bool = True,
    ) -> list[Asset]:
        """
        Return assets belonging to a specific asset type.

        Asset type normalization is performed before querying.
        """
        asset_type = self._normalize_asset_type(asset_type)

        query = self.db.query(self.model).filter(
            self.model.asset_type == asset_type,
        )

        if active_only:
            query = query.filter(
                self.model.is_active.is_(True),
            )

        return (
            query
            .order_by(
                self.model.name.asc(),
                self.model.id.asc(),
            )
            .all()
        )

    def get_asset_by_symbol(
        self,
        symbol: str,
        market: str | None = None,
        *,
        active_only: bool = True,
    ) -> Asset | None:
        """
        Retrieve an asset by canonical symbol and optional market.

        When market is supplied:
            symbol + market identify the asset.

        When market is omitted:
            only an asset whose market is NULL is considered.

        This avoids ambiguous lookups when the same symbol exists
        on multiple markets.
        """
        symbol = self._normalize_required_symbol(symbol)
        market = self._normalize_market(market)

        query = self.db.query(self.model).filter(
            self.model.symbol.ilike(symbol),
        )

        if market is None:
            query = query.filter(
                self.model.market.is_(None),
            )
        else:
            query = query.filter(
                self.model.market.ilike(market),
            )

        if active_only:
            query = query.filter(
                self.model.is_active.is_(True),
            )

        return (
            query
            .order_by(self.model.id.asc())
            .first()
        )

    # ================================================================
    # CREATE
    # ================================================================

    def create_asset(
        self,
        data: AssetCreate,
    ) -> Asset:
        """
        Create a canonical asset.

        Provider integration fields are intentionally not accepted
        through AssetCreate.
        """
        self._validate_valuation_configuration(
            is_market_backed=data.is_market_backed,
            valuation_method=data.valuation_method,
        )

        asset = self.model(
            name=data.name,
            symbol=data.symbol,
            asset_type=data.asset_type,
            description=data.description,
            market=data.market,
            is_market_backed=data.is_market_backed,
            valuation_method=data.valuation_method,
            pricing_currency=data.pricing_currency,
            unit=data.unit,
            is_active=True,
        )

        self.db.add(asset)

        try:
            # PostgreSQL constraints are evaluated here before commit.
            self.db.flush()

        except IntegrityError as exc:
            self.db.rollback()

            raise ConflictError(
                "An active asset with the same canonical identity "
                "already exists."
            ) from exc

        except SQLAlchemyError as exc:
            self.db.rollback()

            raise FinovaError(
                "Failed to create asset."
            ) from exc

        return self.commit(asset)

    # ================================================================
    # UPDATE
    # ================================================================

    def update_asset(
        self,
        asset_id: int,
        data: AssetUpdate,
    ) -> Asset:
        """
        Apply a partial update to an asset.

        The final merged state is validated before persistence.

        Provider mapping fields cannot be modified through this
        user-facing method.
        """
        asset = self.require_asset(asset_id)

        updates = data.model_dump(exclude_unset=True)

        # An empty PATCH is intentionally idempotent.
        if not updates:
            return asset

        # ------------------------------------------------------------
        # Determine the complete resulting valuation configuration.
        #
        # This is essential because AssetUpdate may contain only one
        # side of the is_market_backed / valuation_method pair.
        # ------------------------------------------------------------
        final_is_market_backed = updates.get(
            "is_market_backed",
            asset.is_market_backed,
        )

        final_valuation_method = updates.get(
            "valuation_method",
            asset.valuation_method,
        )

        self._validate_valuation_configuration(
            is_market_backed=final_is_market_backed,
            valuation_method=final_valuation_method,
        )

        # ------------------------------------------------------------
        # Apply only fields explicitly supplied by the caller.
        # AssetUpdate does not expose protected provider fields or
        # database-owned fields such as id and timestamps.
        # ------------------------------------------------------------
        for field, value in updates.items():
            setattr(asset, field, value)

        try:
            self.db.flush()

        except IntegrityError as exc:
            self.db.rollback()

            raise ConflictError(
                "The updated asset conflicts with an existing "
                "active asset."
            ) from exc

        except SQLAlchemyError as exc:
            self.db.rollback()

            raise FinovaError(
                "Failed to update asset."
            ) from exc

        return self.commit(asset)

    # ================================================================
    # VALIDATION
    # ================================================================

    def validate_asset(
        self,
        asset_id: int,
        *,
        require_active: bool = True,
    ) -> Asset:
        """
        Validate that an asset exists and, optionally, is active.

        This is useful to other services such as TransactionService
        and HoldingService.
        """
        asset = self.require_asset(asset_id)

        if require_active and not asset.is_active:
            raise ValidationError(
                f"Asset '{asset.name}' is inactive."
            )

        return asset

    # ================================================================
    # DEACTIVATE
    # ================================================================

    def deactivate_asset(
        self,
        asset_id: int,
    ) -> Asset:
        """
        Deactivate an asset without physically deleting it.

        Deactivation preserves historical references from holdings
        and transactions.

        The operation is idempotent.
        """
        asset = self.require_asset(asset_id)

        if not asset.is_active:
            return asset

        asset.is_active = False

        try:
            self.db.flush()

        except SQLAlchemyError as exc:
            self.db.rollback()

            raise FinovaError(
                "Failed to deactivate asset."
            ) from exc

        return self.commit(asset)

    # ================================================================
    # ACTIVATE
    # ================================================================

    def activate_asset(
        self,
        asset_id: int,
    ) -> Asset:
        """
        Reactivate an inactive asset.

        PostgreSQL's partial unique indexes determine whether the
        asset can safely become active again.

        The operation is idempotent.
        """
        asset = self.require_asset(asset_id)

        if asset.is_active:
            return asset

        asset.is_active = True

        try:
            self.db.flush()

        except IntegrityError as exc:
            self.db.rollback()

            raise ConflictError(
                "The asset cannot be activated because an active "
                "asset with the same canonical identity already exists."
            ) from exc

        except SQLAlchemyError as exc:
            self.db.rollback()

            raise FinovaError(
                "Failed to activate asset."
            ) from exc

        return self.commit(asset)

    # ================================================================
    # INTERNAL NORMALIZATION
    # ================================================================

    @staticmethod
    def _normalize_asset_type(
        value: str,
    ) -> str:
        """
        Normalize an asset type.

        The Pydantic schema performs the primary validation.
        This service-level normalization protects service callers
        that may invoke filtering directly.
        """
        if not value:
            raise ValidationError(
                "Asset type is required."
            )

        value = value.strip().upper()

        valid_types = {
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

        if value not in valid_types:
            raise ValidationError(
                f"Invalid asset type '{value}'."
            )

        return value

    @staticmethod
    def _normalize_required_symbol(
        value: str,
    ) -> str:
        """
        Normalize a required symbol.
        """
        if not value:
            raise ValidationError(
                "Symbol is required."
            )

        value = value.strip().upper()

        if not value:
            raise ValidationError(
                "Symbol is required."
            )

        return value

    @staticmethod
    def _normalize_market(
        value: str | None,
    ) -> str | None:
        """
        Normalize an optional market identifier.
        """
        if value is None:
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _validate_valuation_configuration(
        *,
        is_market_backed: bool,
        valuation_method: str,
    ) -> None:
        """
        Validate the complete valuation configuration.

        This service-level check is necessary because PATCH requests
        can provide only one side of the configuration pair.
        """
        if (
            is_market_backed
            and valuation_method != "MARKET"
        ):
            raise ValidationError(
                "Market-backed assets must use MARKET valuation."
            )

        if (
            not is_market_backed
            and valuation_method != "MANUAL"
        ):
            raise ValidationError(
                "Non-market assets must use MANUAL valuation."
            )