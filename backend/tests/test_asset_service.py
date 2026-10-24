import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions.common import (
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetUpdate
from app.services.asset_service import AssetService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_manual_asset(
    db,
    *,
    name="Apple Inc.",
    symbol="AAPL",
    market=None,
    asset_type="STOCK",
    pricing_currency="USD",
    unit="SHARE",
):
    service = AssetService(db)

    return service.create_asset(
        AssetCreate(
            name=name,
            symbol=symbol,
            asset_type=asset_type,
            market=market,
            pricing_currency=pricing_currency,
            unit=unit,
            is_market_backed=False,
            valuation_method="MANUAL",
        )
    )


def create_market_asset(
    db,
    *,
    name="Apple Inc.",
    symbol="AAPL",
    market="NASDAQ",
    asset_type="STOCK",
    pricing_currency="USD",
    unit="SHARE",
):
    service = AssetService(db)

    return service.create_asset(
        AssetCreate(
            name=name,
            symbol=symbol,
            asset_type=asset_type,
            market=market,
            pricing_currency=pricing_currency,
            unit=unit,
            is_market_backed=True,
            valuation_method="MARKET",
        )
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


class TestAssetCreation:
    def test_create_manual_asset(self, db):
        service = AssetService(db)

        asset = service.create_asset(
            AssetCreate(
                name="  Bitcoin  ",
                symbol=" btc ",
                asset_type=" crypto ",
                pricing_currency=" usd ",
                unit=" coin ",
                is_market_backed=False,
                valuation_method=" manual ",
            )
        )

        assert asset.id is not None
        assert asset.name == "Bitcoin"
        assert asset.symbol == "BTC"
        assert asset.asset_type == "CRYPTO"
        assert asset.pricing_currency == "USD"
        assert asset.unit == "COIN"
        assert asset.is_market_backed is False
        assert asset.valuation_method == "MANUAL"
        assert asset.is_active is True
        assert asset.market_data_provider is None
        assert asset.external_asset_id is None

    def test_create_market_backed_asset(self, db):
        asset = create_market_asset(
            db,
            name="Apple Inc.",
            symbol="aapl",
            market="NASDAQ",
        )

        assert asset.id is not None
        assert asset.name == "Apple Inc."
        assert asset.symbol == "AAPL"
        assert asset.market == "NASDAQ"
        assert asset.is_market_backed is True
        assert asset.valuation_method == "MARKET"
        assert asset.is_active is True

    def test_create_rejects_invalid_asset_type(self):
        with pytest.raises(ValueError, match="Invalid asset type"):
            AssetCreate(
                name="Invalid Asset",
                symbol="BAD",
                asset_type="INVALID",
                pricing_currency="USD",
                unit="UNIT",
            )

    def test_create_rejects_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid asset unit"):
            AssetCreate(
                name="Invalid Asset",
                symbol="BAD",
                asset_type="OTHER",
                pricing_currency="USD",
                unit="INVALID",
            )

    def test_create_rejects_inconsistent_market_valuation_configuration(self):
        with pytest.raises(
            ValueError,
            match="Market-backed assets must use MARKET valuation",
        ):
            AssetCreate(
                name="Apple Inc.",
                symbol="AAPL",
                asset_type="STOCK",
                pricing_currency="USD",
                unit="SHARE",
                is_market_backed=True,
                valuation_method="MANUAL",
            )

    def test_create_rejects_inconsistent_manual_valuation_configuration(self):
        with pytest.raises(
            ValueError,
            match="Non-market assets must use MANUAL valuation",
        ):
            AssetCreate(
                name="Apple Inc.",
                symbol="AAPL",
                asset_type="STOCK",
                pricing_currency="USD",
                unit="SHARE",
                is_market_backed=False,
                valuation_method="MARKET",
            )

    def test_duplicate_active_symbol_without_market_is_rejected(self, db):
        create_manual_asset(
            db,
            name="Apple Inc.",
            symbol="AAPL",
            market=None,
        )

        with pytest.raises(ConflictError):
            create_manual_asset(
                db,
                name="Another Apple",
                symbol="aapl",
                market=None,
            )

    def test_duplicate_active_symbol_and_market_is_rejected(self, db):
        create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        with pytest.raises(ConflictError):
            create_market_asset(
                db,
                name="Another Apple",
                symbol="aapl",
                market="nasdaq",
            )

    def test_same_symbol_on_different_markets_is_allowed(self, db):
        nasdaq = create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        nyse = create_market_asset(
            db,
            name="Apple NYSE",
            symbol="AAPL",
            market="NYSE",
        )

        assert nasdaq.id != nyse.id

    def test_symbol_without_market_and_symbol_with_market_are_distinct(
        self,
        db,
    ):
        no_market = create_manual_asset(
            db,
            name="Apple Generic",
            symbol="AAPL",
            market=None,
        )

        with_market = create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        assert no_market.id != with_market.id

    def test_inactive_duplicate_identity_can_be_replaced_by_active_asset(
        self,
        db,
    ):
        service = AssetService(db)

        original = create_market_asset(
            db,
            name="Old Apple",
            symbol="AAPL",
            market="NASDAQ",
        )

        service.deactivate_asset(original.id)

        replacement = create_market_asset(
            db,
            name="New Apple",
            symbol="AAPL",
            market="NASDAQ",
        )

        assert replacement.id != original.id
        assert replacement.is_active is True
        assert original.is_active is False


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class TestAssetRetrieval:
    def test_get_asset_returns_asset(self, db):
        service = AssetService(db)

        created = create_manual_asset(db)

        result = service.get_asset(created.id)

        assert result is not None
        assert result.id == created.id

    def test_get_missing_asset_returns_none(self, db):
        service = AssetService(db)

        result = service.get_asset(999999)

        assert result is None

    def test_require_missing_asset_raises_not_found(self, db):
        service = AssetService(db)

        with pytest.raises(NotFoundError):
            service.require_asset(999999)

    def test_get_active_asset_hides_inactive_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)
        service.deactivate_asset(asset.id)

        assert service.get_asset(asset.id, active_only=True) is None
        assert service.get_asset(asset.id, active_only=False) is not None

    def test_require_active_asset_rejects_inactive_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)
        service.deactivate_asset(asset.id)

        with pytest.raises(NotFoundError):
            service.require_asset(asset.id, active_only=True)

    def test_list_assets_returns_active_assets_by_default(self, db):
        service = AssetService(db)

        active = create_manual_asset(
            db,
            name="Active Asset",
            symbol="ACT",
        )

        inactive = create_manual_asset(
            db,
            name="Inactive Asset",
            symbol="INA",
        )

        service.deactivate_asset(inactive.id)

        assets = service.list_assets()

        ids = {asset.id for asset in assets}

        assert active.id in ids
        assert inactive.id not in ids

    def test_list_assets_can_include_inactive_assets(self, db):
        service = AssetService(db)

        active = create_manual_asset(
            db,
            name="Active Asset",
            symbol="ACT",
        )

        inactive = create_manual_asset(
            db,
            name="Inactive Asset",
            symbol="INA",
        )

        service.deactivate_asset(inactive.id)

        assets = service.list_assets(active_only=False)

        ids = {asset.id for asset in assets}

        assert active.id in ids
        assert inactive.id in ids

    def test_list_assets_filters_by_asset_type(self, db):
        service = AssetService(db)

        stock = create_manual_asset(
            db,
            name="Apple",
            symbol="AAPL",
            asset_type="STOCK",
        )

        crypto = create_manual_asset(
            db,
            name="Bitcoin",
            symbol="BTC",
            asset_type="CRYPTO",
        )

        assets = service.list_assets(asset_type="crypto")

        ids = {asset.id for asset in assets}

        assert crypto.id in ids
        assert stock.id not in ids

    def test_get_assets_by_type_filters_correctly(self, db):
        service = AssetService(db)

        stock = create_manual_asset(
            db,
            name="Apple",
            symbol="AAPL",
            asset_type="STOCK",
        )

        etf = create_manual_asset(
            db,
            name="SPY",
            symbol="SPY",
            asset_type="ETF",
        )

        assets = service.get_assets_by_type("stock")

        ids = {asset.id for asset in assets}

        assert stock.id in ids
        assert etf.id not in ids

    def test_get_asset_by_symbol_without_market_matches_only_null_market(
        self,
        db,
    ):
        service = AssetService(db)

        generic = create_manual_asset(
            db,
            name="Generic Apple",
            symbol="AAPL",
            market=None,
        )

        create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        result = service.get_asset_by_symbol("aapl")

        assert result is not None
        assert result.id == generic.id
        assert result.market is None

    def test_get_asset_by_symbol_with_market_matches_correct_market(
        self,
        db,
    ):
        service = AssetService(db)

        nasdaq = create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        create_market_asset(
            db,
            name="Apple NYSE",
            symbol="AAPL",
            market="NYSE",
        )

        result = service.get_asset_by_symbol(
            "aapl",
            market="nasdaq",
        )

        assert result is not None
        assert result.id == nasdaq.id

    def test_get_asset_by_symbol_does_not_return_inactive_by_default(
        self,
        db,
    ):
        service = AssetService(db)

        asset = create_manual_asset(
            db,
            symbol="AAPL",
        )

        service.deactivate_asset(asset.id)

        result = service.get_asset_by_symbol("AAPL")

        assert result is None

    def test_get_asset_by_symbol_can_include_inactive_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(
            db,
            symbol="AAPL",
        )

        service.deactivate_asset(asset.id)

        result = service.get_asset_by_symbol(
            "AAPL",
            active_only=False,
        )

        assert result is not None
        assert result.id == asset.id


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestAssetValidation:
    def test_validate_active_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        result = service.validate_asset(asset.id)

        assert result.id == asset.id

    def test_validate_missing_asset_raises_not_found(self, db):
        service = AssetService(db)

        with pytest.raises(NotFoundError):
            service.validate_asset(999999)

    def test_validate_inactive_asset_raises_validation_error(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)
        service.deactivate_asset(asset.id)

        with pytest.raises(ValidationError):
            service.validate_asset(asset.id)

    def test_validate_inactive_asset_can_be_allowed_explicitly(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)
        service.deactivate_asset(asset.id)

        result = service.validate_asset(
            asset.id,
            require_active=False,
        )

        assert result.id == asset.id


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


class TestAssetUpdates:
    def test_partial_update_changes_only_supplied_fields(self, db):
        service = AssetService(db)

        asset = create_manual_asset(
            db,
            name="Apple Inc.",
            symbol="AAPL",
            asset_type="STOCK",
            pricing_currency="USD",
            unit="SHARE",
        )

        updated = service.update_asset(
            asset.id,
            AssetUpdate(
                name="Apple Corporation",
                description="Updated description",
            ),
        )

        assert updated.name == "Apple Corporation"
        assert updated.description == "Updated description"
        assert updated.symbol == "AAPL"
        assert updated.asset_type == "STOCK"
        assert updated.pricing_currency == "USD"
        assert updated.unit == "SHARE"

    def test_empty_update_is_idempotent(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        updated = service.update_asset(
            asset.id,
            AssetUpdate(),
        )

        assert updated.id == asset.id
        assert updated.name == asset.name
        assert updated.symbol == asset.symbol

    def test_update_normalizes_fields(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        updated = service.update_asset(
            asset.id,
            AssetUpdate(
                name="  Microsoft Corporation  ",
                symbol=" msft ",
                asset_type=" stock ",
                pricing_currency=" eur ",
                unit=" share ",
            ),
        )

        assert updated.name == "Microsoft Corporation"
        assert updated.symbol == "MSFT"
        assert updated.asset_type == "STOCK"
        assert updated.pricing_currency == "EUR"
        assert updated.unit == "SHARE"

    def test_update_can_clear_symbol(self, db):
        service = AssetService(db)

        asset = create_manual_asset(
            db,
            symbol="AAPL",
        )

        updated = service.update_asset(
            asset.id,
            AssetUpdate(symbol=None),
        )

        assert updated.symbol is None

    def test_update_can_clear_market(self, db):
        service = AssetService(db)

        asset = create_market_asset(
            db,
            symbol="AAPL",
            market="NASDAQ",
        )

        updated = service.update_asset(
            asset.id,
            AssetUpdate(market=None),
        )

        assert updated.market is None

    def test_update_can_change_market(self, db):
        service = AssetService(db)

        asset = create_market_asset(
            db,
            symbol="AAPL",
            market="NASDAQ",
        )

        updated = service.update_asset(
            asset.id,
            AssetUpdate(market="NYSE"),
        )

        assert updated.market == "NYSE"

    def test_update_duplicate_identity_raises_conflict(self, db):
        service = AssetService(db)

        first = create_market_asset(
            db,
            name="Apple NASDAQ",
            symbol="AAPL",
            market="NASDAQ",
        )

        second = create_market_asset(
            db,
            name="Microsoft NASDAQ",
            symbol="MSFT",
            market="NASDAQ",
        )

        with pytest.raises(ConflictError):
            service.update_asset(
                second.id,
                AssetUpdate(symbol=first.symbol),
            )

    def test_update_symbol_preserves_other_fields(self, db):
        service = AssetService(db)

        asset = create_manual_asset(
            db,
            name="Original Name",
            symbol="ORIG",
            asset_type="STOCK",
            pricing_currency="USD",
            unit="SHARE",
        )

        updated = service.update_asset(
            asset.id,
            AssetUpdate(symbol="NEW"),
        )

        assert updated.symbol == "NEW"
        assert updated.name == "Original Name"
        assert updated.asset_type == "STOCK"
        assert updated.pricing_currency == "USD"
        assert updated.unit == "SHARE"

    def test_changing_only_market_backed_flag_rejects_incompatible_state(
        self,
        db,
    ):
        service = AssetService(db)

        asset = create_manual_asset(db)

        with pytest.raises(ValidationError):
            service.update_asset(
                asset.id,
                AssetUpdate(is_market_backed=True),
            )

    def test_changing_only_valuation_method_rejects_incompatible_state(
        self,
        db,
    ):
        service = AssetService(db)

        asset = create_manual_asset(db)

        with pytest.raises(ValidationError):
            service.update_asset(
                asset.id,
                AssetUpdate(valuation_method="MARKET"),
            )

    def test_market_backed_configuration_can_be_changed_atomically(
        self,
        db,
    ):
        service = AssetService(db)

        asset = create_manual_asset(db)

        updated = service.update_asset(
            asset.id,
            AssetUpdate(
                is_market_backed=True,
                valuation_method="MARKET",
            ),
        )

        assert updated.is_market_backed is True
        assert updated.valuation_method == "MARKET"

    def test_manual_configuration_can_be_changed_atomically(
        self,
        db,
    ):
        service = AssetService(db)

        asset = create_market_asset(db)

        updated = service.update_asset(
            asset.id,
            AssetUpdate(
                is_market_backed=False,
                valuation_method="MANUAL",
            ),
        )

        assert updated.is_market_backed is False
        assert updated.valuation_method == "MANUAL"

    def test_update_missing_asset_raises_not_found(self, db):
        service = AssetService(db)

        with pytest.raises(NotFoundError):
            service.update_asset(
                999999,
                AssetUpdate(name="Does Not Exist"),
            )

    def test_provider_mapping_is_not_part_of_update_schema(self):
        fields = AssetUpdate.model_fields

        assert "market_data_provider" not in fields
        assert "external_asset_id" not in fields


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestAssetLifecycle:
    def test_deactivate_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        result = service.deactivate_asset(asset.id)

        assert result.is_active is False

    def test_deactivate_asset_is_idempotent(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        first = service.deactivate_asset(asset.id)
        second = service.deactivate_asset(asset.id)

        assert first.is_active is False
        assert second.is_active is False
        assert second.id == asset.id

    def test_deactivate_missing_asset_raises_not_found(self, db):
        service = AssetService(db)

        with pytest.raises(NotFoundError):
            service.deactivate_asset(999999)

    def test_activate_asset(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        service.deactivate_asset(asset.id)

        result = service.activate_asset(asset.id)

        assert result.is_active is True

    def test_activate_asset_is_idempotent(self, db):
        service = AssetService(db)

        asset = create_manual_asset(db)

        first = service.activate_asset(asset.id)
        second = service.activate_asset(asset.id)

        assert first.is_active is True
        assert second.is_active is True
        assert second.id == asset.id

    def test_activate_missing_asset_raises_not_found(self, db):
        service = AssetService(db)

        with pytest.raises(NotFoundError):
            service.activate_asset(999999)

    def test_reactivation_conflict_is_rejected(self, db):
        service = AssetService(db)

        original = create_market_asset(
            db,
            name="Original Apple",
            symbol="AAPL",
            market="NASDAQ",
        )

        service.deactivate_asset(original.id)

        replacement = create_market_asset(
            db,
            name="Replacement Apple",
            symbol="AAPL",
            market="NASDAQ",
        )

        assert replacement.is_active is True

        with pytest.raises(ConflictError):
            service.activate_asset(original.id)

        # The failed activation must not leave the original asset active.
        refreshed = service.get_asset(
            original.id,
            active_only=False,
        )

        assert refreshed is not None
        assert refreshed.is_active is False


# ---------------------------------------------------------------------------
# PostgreSQL database constraints
# ---------------------------------------------------------------------------


class TestAssetDatabaseConstraints:
    def test_database_enforces_valuation_configuration(self, db):
        asset = Asset(
            name="Invalid Market Asset",
            symbol="BAD",
            asset_type="STOCK",
            pricing_currency="USD",
            unit="SHARE",
            is_market_backed=True,
            valuation_method="MANUAL",
            is_active=True,
        )

        db.add(asset)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    def test_database_enforces_provider_external_id_pair(self, db):
        asset = Asset(
            name="Invalid Provider Mapping",
            symbol="PROV",
            asset_type="OTHER",
            pricing_currency="USD",
            unit="UNIT",
            is_market_backed=False,
            valuation_method="MANUAL",
            market_data_provider="some_provider",
            external_asset_id=None,
            is_active=True,
        )

        db.add(asset)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    def test_database_enforces_reverse_provider_external_id_pair(self, db):
        asset = Asset(
            name="Invalid Provider Mapping",
            symbol="PROV2",
            asset_type="OTHER",
            pricing_currency="USD",
            unit="UNIT",
            is_market_backed=False,
            valuation_method="MANUAL",
            market_data_provider=None,
            external_asset_id="external-123",
            is_active=True,
        )

        db.add(asset)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    def test_database_enforces_active_symbol_market_uniqueness(self, db):
        first = Asset(
            name="First Apple",
            symbol="AAPL",
            asset_type="STOCK",
            market="NASDAQ",
            pricing_currency="USD",
            unit="SHARE",
            is_market_backed=True,
            valuation_method="MARKET",
            is_active=True,
        )

        db.add(first)
        db.flush()

        duplicate = Asset(
            name="Duplicate Apple",
            symbol="aapl",
            asset_type="STOCK",
            market="nasdaq",
            pricing_currency="USD",
            unit="SHARE",
            is_market_backed=True,
            valuation_method="MARKET",
            is_active=True,
        )

        db.add(duplicate)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()