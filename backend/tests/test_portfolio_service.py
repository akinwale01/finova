import pytest

from backend.app.exceptions.common import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.portfolio import Portfolio
from backend.app.models.user import User
from backend.app.schemas.portfolio import PortfolioCreate, PortfolioUpdate
from backend.app.services.portfolio_service import PortfolioService


def create_test_user(
    db,
    *,
    email: str,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash="test-password-hash",
        is_active=is_active,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_test_portfolio(
    db,
    *,
    user_id: int,
    name: str,
    is_active: bool = True,
) -> Portfolio:
    portfolio = Portfolio(
        user_id=user_id,
        name=name,
        is_active=is_active,
    )

    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return portfolio


# ----------------------------------------------------------------------
# Creation
# ----------------------------------------------------------------------


def test_create_portfolio(db):
    user = create_test_user(
        db,
        email="portfolio-create@example.com",
    )

    service = PortfolioService(db)

    portfolio = service.create_portfolio(
        user.id,
        PortfolioCreate(name="Long-Term Investments"),
    )

    assert portfolio.id is not None
    assert portfolio.user_id == user.id
    assert portfolio.name == "Long-Term Investments"
    assert portfolio.is_active is True


def test_create_portfolio_strips_name_whitespace(db):
    user = create_test_user(
        db,
        email="portfolio-whitespace@example.com",
    )

    service = PortfolioService(db)

    portfolio = service.create_portfolio(
        user.id,
        PortfolioCreate(name="  Crypto Portfolio  "),
    )

    assert portfolio.name == "Crypto Portfolio"


def test_create_portfolio_missing_user(db):
    service = PortfolioService(db)

    with pytest.raises(NotFoundError):
        service.create_portfolio(
            999999,
            PortfolioCreate(name="Portfolio"),
        )


def test_create_portfolio_inactive_user(db):
    user = create_test_user(
        db,
        email="portfolio-inactive-user@example.com",
        is_active=False,
    )

    service = PortfolioService(db)

    with pytest.raises(ValidationError):
        service.create_portfolio(
            user.id,
            PortfolioCreate(name="Portfolio"),
        )


def test_duplicate_active_portfolio_name_is_rejected_case_insensitively(
    db,
):
    user = create_test_user(
        db,
        email="portfolio-duplicate@example.com",
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="My Investments",
    )

    service = PortfolioService(db)

    with pytest.raises(ConflictError):
        service.create_portfolio(
            user.id,
            PortfolioCreate(name="my investments"),
        )


def test_same_name_is_allowed_for_different_users(db):
    user_one = create_test_user(
        db,
        email="portfolio-user-one@example.com",
    )

    user_two = create_test_user(
        db,
        email="portfolio-user-two@example.com",
    )

    service = PortfolioService(db)

    first = service.create_portfolio(
        user_one.id,
        PortfolioCreate(name="Investments"),
    )

    second = service.create_portfolio(
        user_two.id,
        PortfolioCreate(name="Investments"),
    )

    assert first.id != second.id
    assert first.user_id != second.user_id


def test_same_name_allowed_when_existing_portfolio_is_inactive(
    db,
):
    user = create_test_user(
        db,
        email="portfolio-inactive-name@example.com",
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Investments",
        is_active=False,
    )

    service = PortfolioService(db)

    portfolio = service.create_portfolio(
        user.id,
        PortfolioCreate(name="Investments"),
    )

    assert portfolio.is_active is True


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------


def test_get_owned_portfolio(db):
    user = create_test_user(
        db,
        email="portfolio-get@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Investments",
    )

    service = PortfolioService(db)

    result = service.get_portfolio(
        user.id,
        portfolio.id,
    )

    assert result is not None
    assert result.id == portfolio.id


def test_get_other_users_portfolio_returns_none(db):
    owner = create_test_user(
        db,
        email="portfolio-owner@example.com",
    )

    other_user = create_test_user(
        db,
        email="portfolio-other@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=owner.id,
        name="Private Portfolio",
    )

    service = PortfolioService(db)

    result = service.get_portfolio(
        other_user.id,
        portfolio.id,
    )

    assert result is None


def test_get_missing_portfolio_returns_none(db):
    user = create_test_user(
        db,
        email="portfolio-missing@example.com",
    )

    service = PortfolioService(db)

    result = service.get_portfolio(
        user.id,
        999999,
    )

    assert result is None


def test_require_portfolio_returns_owned_portfolio(db):
    user = create_test_user(
        db,
        email="portfolio-require@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Required Portfolio",
    )

    service = PortfolioService(db)

    result = service.require_portfolio(
        user.id,
        portfolio.id,
    )

    assert result.id == portfolio.id


def test_require_other_users_portfolio_raises_not_found(db):
    owner = create_test_user(
        db,
        email="portfolio-require-owner@example.com",
    )

    other_user = create_test_user(
        db,
        email="portfolio-require-other@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=owner.id,
        name="Private Portfolio",
    )

    service = PortfolioService(db)

    with pytest.raises(NotFoundError):
        service.require_portfolio(
            other_user.id,
            portfolio.id,
        )


# ----------------------------------------------------------------------
# Listing
# ----------------------------------------------------------------------


def test_list_portfolios_returns_only_owned_portfolios(db):
    user_one = create_test_user(
        db,
        email="portfolio-list-one@example.com",
    )

    user_two = create_test_user(
        db,
        email="portfolio-list-two@example.com",
    )

    create_test_portfolio(
        db,
        user_id=user_one.id,
        name="Portfolio A",
    )

    create_test_portfolio(
        db,
        user_id=user_one.id,
        name="Portfolio B",
    )

    create_test_portfolio(
        db,
        user_id=user_two.id,
        name="Other Portfolio",
    )

    service = PortfolioService(db)

    portfolios = service.list_portfolios(user_one.id)

    assert len(portfolios) == 2
    assert {portfolio.name for portfolio in portfolios} == {
        "Portfolio A",
        "Portfolio B",
    }


def test_list_portfolios_active_only(db):
    user = create_test_user(
        db,
        email="portfolio-active-list@example.com",
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Active Portfolio",
        is_active=True,
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Inactive Portfolio",
        is_active=False,
    )

    service = PortfolioService(db)

    portfolios = service.list_portfolios(
        user.id,
        active_only=True,
    )

    assert len(portfolios) == 1
    assert portfolios[0].name == "Active Portfolio"


def test_list_portfolios_includes_inactive_by_default(db):
    user = create_test_user(
        db,
        email="portfolio-list-all@example.com",
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Active Portfolio",
        is_active=True,
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Inactive Portfolio",
        is_active=False,
    )

    service = PortfolioService(db)

    portfolios = service.list_portfolios(user.id)

    assert len(portfolios) == 2


# ----------------------------------------------------------------------
# Updates
# ----------------------------------------------------------------------


def test_update_portfolio_name(db):
    user = create_test_user(
        db,
        email="portfolio-update-name@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Old Name",
    )

    service = PortfolioService(db)

    updated = service.update_portfolio(
        user.id,
        portfolio.id,
        PortfolioUpdate(name="New Name"),
    )

    assert updated.name == "New Name"
    assert updated.is_active is True


def test_update_portfolio_status(db):
    user = create_test_user(
        db,
        email="portfolio-update-status@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
    )

    service = PortfolioService(db)

    updated = service.update_portfolio(
        user.id,
        portfolio.id,
        PortfolioUpdate(is_active=False),
    )

    assert updated.is_active is False


def test_update_multiple_fields(db):
    user = create_test_user(
        db,
        email="portfolio-update-multiple@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Original",
    )

    service = PortfolioService(db)

    updated = service.update_portfolio(
        user.id,
        portfolio.id,
        PortfolioUpdate(
            name="Updated",
            is_active=False,
        ),
    )

    assert updated.name == "Updated"
    assert updated.is_active is False


def test_update_preserves_unspecified_fields(db):
    user = create_test_user(
        db,
        email="portfolio-preserve@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Original",
        is_active=True,
    )

    service = PortfolioService(db)

    updated = service.update_portfolio(
        user.id,
        portfolio.id,
        PortfolioUpdate(name="Updated"),
    )

    assert updated.name == "Updated"
    assert updated.is_active is True


def test_empty_update_is_idempotent(db):
    user = create_test_user(
        db,
        email="portfolio-empty-update@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
    )

    original_updated_at = portfolio.updated_at

    service = PortfolioService(db)

    updated = service.update_portfolio(
        user.id,
        portfolio.id,
        PortfolioUpdate(),
    )

    assert updated.id == portfolio.id
    assert updated.name == "Portfolio"
    assert updated.is_active is True
    assert updated.updated_at == original_updated_at


def test_update_other_users_portfolio_is_rejected(db):
    owner = create_test_user(
        db,
        email="portfolio-update-owner@example.com",
    )

    other_user = create_test_user(
        db,
        email="portfolio-update-other@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=owner.id,
        name="Original",
    )

    service = PortfolioService(db)

    with pytest.raises(NotFoundError):
        service.update_portfolio(
            other_user.id,
            portfolio.id,
            PortfolioUpdate(name="Hacked"),
        )

    db.refresh(portfolio)

    assert portfolio.name == "Original"
    assert portfolio.user_id == owner.id


def test_update_duplicate_active_name_is_rejected(db):
    user = create_test_user(
        db,
        email="portfolio-update-duplicate@example.com",
    )

    first = create_test_portfolio(
        db,
        user_id=user.id,
        name="First",
    )

    second = create_test_portfolio(
        db,
        user_id=user.id,
        name="Second",
    )

    service = PortfolioService(db)

    with pytest.raises(ConflictError):
        service.update_portfolio(
            user.id,
            second.id,
            PortfolioUpdate(name=first.name),
        )

    db.refresh(second)

    assert second.name == "Second"


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------


def test_deactivate_portfolio(db):
    user = create_test_user(
        db,
        email="portfolio-deactivate@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
    )

    service = PortfolioService(db)

    result = service.deactivate_portfolio(
        user.id,
        portfolio.id,
    )

    assert result.is_active is False


def test_deactivate_portfolio_is_idempotent(db):
    user = create_test_user(
        db,
        email="portfolio-deactivate-idempotent@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
        is_active=False,
    )

    service = PortfolioService(db)

    result = service.deactivate_portfolio(
        user.id,
        portfolio.id,
    )

    assert result.is_active is False


def test_activate_portfolio(db):
    user = create_test_user(
        db,
        email="portfolio-activate@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
        is_active=False,
    )

    service = PortfolioService(db)

    result = service.activate_portfolio(
        user.id,
        portfolio.id,
    )

    assert result.is_active is True


def test_activate_portfolio_is_idempotent(db):
    user = create_test_user(
        db,
        email="portfolio-activate-idempotent@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=user.id,
        name="Portfolio",
        is_active=True,
    )

    service = PortfolioService(db)

    result = service.activate_portfolio(
        user.id,
        portfolio.id,
    )

    assert result.is_active is True


def test_reactivate_conflicting_portfolio_is_rejected(db):
    user = create_test_user(
        db,
        email="portfolio-reactivate-conflict@example.com",
    )

    inactive = create_test_portfolio(
        db,
        user_id=user.id,
        name="Investments",
        is_active=False,
    )

    create_test_portfolio(
        db,
        user_id=user.id,
        name="Investments",
        is_active=True,
    )

    service = PortfolioService(db)

    with pytest.raises(ConflictError):
        service.activate_portfolio(
            user.id,
            inactive.id,
        )

    db.refresh(inactive)

    assert inactive.is_active is False


def test_activate_other_users_portfolio_is_rejected(db):
    owner = create_test_user(
        db,
        email="portfolio-activate-owner@example.com",
    )

    other_user = create_test_user(
        db,
        email="portfolio-activate-other@example.com",
    )

    portfolio = create_test_portfolio(
        db,
        user_id=owner.id,
        name="Portfolio",
        is_active=False,
    )

    service = PortfolioService(db)

    with pytest.raises(NotFoundError):
        service.activate_portfolio(
            other_user.id,
            portfolio.id,
        )

    db.refresh(portfolio)

    assert portfolio.is_active is False