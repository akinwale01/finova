from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.exceptions import FinovaError, NotFoundError




ModelType = TypeVar("ModelType")


class BaseService(Generic[ModelType]):
    """
    Common foundation for all Finova database services.

    BaseService provides reusable database operations that are
    independent of a specific business domain.

    Individual services such as UserService, AccountService,
    PortfolioService, AssetService, TransactionService,
    ScheduledTransactionService, and HoldingService should
    contain their own business rules and authorization logic.

    BaseService deliberately does NOT:
        - perform user authorization
        - enforce ownership relationships
        - implement model-specific validation
        - calculate financial values
        - contain domain-specific business rules

    Those responsibilities belong to the appropriate service.
    """

    model: type[ModelType]

    def __init__(self, db: Session) -> None:
        """
        Initialize the service with an active SQLAlchemy session.

        The service does not create or close the session.
        Session lifecycle is owned by the application/request layer.
        """
        self.db = db

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def get_by_id(self, record_id: int) -> ModelType | None:
        """
        Retrieve a record by primary key.

        Returns:
            The model instance if found.
            None if no record exists.
        """
        return self.db.get(self.model, record_id)

    def require_by_id(
        self,
        record_id: int,
        resource_name: str | None = None,
    ) -> ModelType:
        """
        Retrieve a record by primary key or raise NotFoundError.

        This is useful when the requested record must exist.

        Example:
            holding = self.require_by_id(
                holding_id,
                "Holding",
            )
        """
        record = self.get_by_id(record_id)

        if record is None:
            name = resource_name or self.model.__name__

            raise NotFoundError(
                f"{name} with id {record_id} was not found."
            )

        return record

    # =========================================================
    # PERSISTENCE
    # =========================================================

    def add(self, record: ModelType) -> ModelType:
        """
        Add a model instance to the current database session.

        This method does not commit the transaction.
        """
        self.db.add(record)
        return record

    def flush(self) -> None:
        """
        Flush pending changes to the database without committing.

        Flush is useful when database-generated values, such as
        primary keys, are required before the surrounding
        transaction is committed.
        """
        self.db.flush()

    def refresh(self, record: ModelType) -> ModelType:
        """
        Refresh a model instance from the database.

        This ensures the object reflects the persisted database
        state after a successful flush/commit.
        """
        self.db.refresh(record)
        return record

    def commit(self, record: ModelType | None = None) -> ModelType | None:
        """
        Commit the current transaction.

        If a record is supplied, refresh it after the commit so
        callers receive the persisted database state.
        """
        try:
            self.db.commit()

            if record is not None:
                self.db.refresh(record)

            return record

        except SQLAlchemyError as exc:
            self.db.rollback()

            raise FinovaError(
                "Database transaction failed."
            ) from exc

    def rollback(self) -> None:
        """
        Roll back the current database transaction.
        """
        self.db.rollback()

    # =========================================================
    # DELETE
    # =========================================================

    def delete(self, record: ModelType) -> None:
        """
        Mark a record for deletion.

        The deletion is not committed automatically.

        The individual service decides whether deletion is
        permitted according to its business rules.
        """
        self.db.delete(record)