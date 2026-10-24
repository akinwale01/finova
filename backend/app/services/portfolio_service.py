from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.schemas.portfolio import PortfolioCreate, PortfolioUpdate
from app.services.base_service import BaseService
from app.exceptions.common import (
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from app.models.user import User


class PortfolioService(BaseService[Portfolio]):
    """
    Business-logic and authorization layer for portfolios.

    Portfolio ownership is always enforced through user_id for
    user-facing operations.

    Normal portfolio deletion is intentionally not supported.
    Portfolios use soft deletion through is_active=False so that
    financial history remains preserved.
    """

    model = Portfolio

    def __init__(self, db: Session):
        super().__init__(db)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
    ) -> Portfolio | None:
        """
        Return a portfolio only when it belongs to the specified user.

        Returning None for another user's portfolio prevents the
        service from exposing whether that resource exists.
        """
        return (
            self.db.query(self.model)
            .filter(
                self.model.id == portfolio_id,
                self.model.user_id == user_id,
            )
            .first()
        )

    def require_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
    ) -> Portfolio:
        """
        Return an owned portfolio or raise NotFoundError.

        Ownership failures intentionally appear as not-found rather
        than authorization errors to avoid resource enumeration.
        """
        portfolio = self.get_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise NotFoundError("Portfolio not found.")

        return portfolio

    def list_portfolios(
        self,
        user_id: int,
        *,
        active_only: bool = False,
    ) -> list[Portfolio]:
        """
        Return portfolios belonging exclusively to the specified user.

        Results are returned in deterministic ID order.
        """
        query = self.db.query(self.model).filter(
            self.model.user_id == user_id,
        )

        if active_only:
            query = query.filter(
                self.model.is_active.is_(True),
            )

        return query.order_by(self.model.id.asc()).all()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_portfolio(
        self,
        user_id: int,
        data: PortfolioCreate,
    ) -> Portfolio:
        """
        Create a portfolio for an active user.

        user_id comes from the authenticated application context and
        is never accepted from PortfolioCreate.
        """
        self._ensure_active_user(user_id)

        portfolio = self.model(
            user_id=user_id,
            name=data.name,
            is_active=True,
        )

        self.db.add(portfolio)

        try:
            # Flush first so PostgreSQL constraints are evaluated here.
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "An active portfolio with this name already exists."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Failed to create portfolio."
            ) from exc

        return self.commit(portfolio)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
        data: PortfolioUpdate,
    ) -> Portfolio:
        """
        Apply a partial update to an owned portfolio.

        Only fields exposed by PortfolioUpdate can reach this method,
        so database-owned fields such as id, user_id and timestamps
        cannot be changed through the service.
        """
        portfolio = self.require_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        updates = data.model_dump(exclude_unset=True)

        # Empty PATCH requests are intentionally idempotent.
        if not updates:
            return portfolio

        for field, value in updates.items():
            setattr(portfolio, field, value)

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "An active portfolio with this name already exists."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Failed to update portfolio."
            ) from exc

        return self.commit(portfolio)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def deactivate_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
    ) -> Portfolio:
        """
        Deactivate an owned portfolio.

        Deactivation is idempotent.
        """
        portfolio = self.require_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        if not portfolio.is_active:
            return portfolio

        portfolio.is_active = False

        try:
            self.db.flush()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Failed to deactivate portfolio."
            ) from exc

        return self.commit(portfolio)

    def activate_portfolio(
        self,
        user_id: int,
        portfolio_id: int,
    ) -> Portfolio:
        """
        Activate an owned portfolio.

        Reactivation is subject to PostgreSQL's partial unique index.
        Therefore an inactive portfolio cannot be reactivated when
        another active portfolio owned by the same user already has
        the same case-insensitive name.
        """
        portfolio = self.require_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        if portfolio.is_active:
            return portfolio

        portfolio.is_active = True

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "An active portfolio with this name already exists."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Failed to activate portfolio."
            ) from exc

        return self.commit(portfolio)

    # ------------------------------------------------------------------
    # Internal validation
    # ------------------------------------------------------------------

    def _ensure_active_user(self, user_id: int) -> User:
        """
        Ensure the target user exists and is active.

        Portfolio creation must never create resources for inactive
        or nonexistent users.
        """
        user = (
            self.db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None:
            raise NotFoundError("User not found.")

        if not user.is_active:
            raise ValidationError(
                "Inactive users cannot create portfolios."
            )

        return user