from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.exceptions.common import (
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.account import Account
from backend.app.models.asset import Asset
from backend.app.models.portfolio import Portfolio
from backend.app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)
from backend.app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
)
from backend.app.services.base_service import BaseService


class TransactionService(BaseService[Transaction]):
    """
    Service layer for financial transactions.

    Finova is a financial aggregation and intelligence system. It records
    real-world financial events but does not execute, custody, or directly
    mutate the user's money.

    Transaction ownership is derived from user-owned resources because the
    Transaction model intentionally does not contain a user_id.

    Core responsibilities:

    - Validate transaction-type semantics.
    - Validate ownership of referenced portfolios and accounts.
    - Resolve referenced assets.
    - Prevent unauthorized cross-user access.
    - Prevent COMPLETED transactions from referencing inactive resources.
    - Preserve FAILED and CANCELLED historical records.
    - Enforce transaction lifecycle rules.
    - Keep completed financial history immutable.
    - Translate database errors into domain exceptions.

    TransactionService does NOT:

    - mutate Account balances;
    - create/update Holding records;
    - calculate net worth;
    - calculate realized/unrealized P/L;
    - execute external financial operations.

    Those responsibilities belong to the appropriate financial-state or
    deterministic analytics layer.
    """

    model = Transaction

    def __init__(self, db: Session):
        super().__init__(db)

    # =====================================================================
    # RETRIEVAL
    # =====================================================================

    def get_transaction(
        self,
        user_id: int,
        transaction_id: int,
    ) -> Transaction | None:
        """
        Return a transaction only when it belongs to the requesting user.

        Ownership is derived from the transaction's portfolio or
        source/destination accounts.
        """
        self._ensure_valid_user_id(user_id)

        transaction = self.get_by_id(transaction_id)

        if transaction is None:
            return None

        if not self._transaction_belongs_to_user(
            transaction=transaction,
            user_id=user_id,
        ):
            return None

        return transaction

    def require_transaction(
        self,
        user_id: int,
        transaction_id: int,
    ) -> Transaction:
        """
        Return an owned transaction or raise NotFoundError.
        """
        transaction = self.get_transaction(
            user_id=user_id,
            transaction_id=transaction_id,
        )

        if transaction is None:
            raise NotFoundError(
                f"Transaction {transaction_id} was not found."
            )

        return transaction

    def list_transactions(
        self,
        user_id: int,
        *,
        portfolio_id: int | None = None,
        account_id: int | None = None,
        asset_id: int | None = None,
        transaction_type: TransactionType | None = None,
        status: TransactionStatus | None = None,
    ) -> list[Transaction]:
        """
        Return transactions visible to the requesting user.

        Portfolio and account filters are ownership-checked before being
        used in the transaction query.
        """
        self._ensure_valid_user_id(user_id)

        # Ownership-scoped filters must be validated before querying.
        if portfolio_id is not None:
            self._resolve_portfolio(
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

        if account_id is not None:
            self._resolve_account(
                user_id=user_id,
                account_id=account_id,
            )

        statement = (
            select(Transaction)
            .outerjoin(
                Portfolio,
                Transaction.portfolio_id == Portfolio.id,
            )
            .outerjoin(
                Account,
                (Transaction.source_account_id == Account.id)
                | (Transaction.destination_account_id == Account.id),
            )
            .where(
                (Portfolio.user_id == user_id)
                | (Account.user_id == user_id)
            )
            .order_by(
                Transaction.transaction_date.desc(),
                Transaction.id.desc(),
            )
        )

        if portfolio_id is not None:
            statement = statement.where(
                Transaction.portfolio_id == portfolio_id
            )

        if account_id is not None:
            statement = statement.where(
                (Transaction.source_account_id == account_id)
                | (Transaction.destination_account_id == account_id)
            )

        if asset_id is not None:
            statement = statement.where(
                Transaction.asset_id == asset_id
            )

        if transaction_type is not None:
            statement = statement.where(
                Transaction.transaction_type == transaction_type.value
            )

        if status is not None:
            statement = statement.where(
                Transaction.status == status.value
            )

        return list(
            self.db.scalars(statement).unique().all()
        )

    # =====================================================================
    # CREATION
    # =====================================================================

    def create_transaction(
        self,
        user_id: int,
        data: TransactionCreate,
    ) -> Transaction:
        """
        Create a transaction after validating its complete domain state.

        TransactionService records the financial event only. It does not
        directly mutate accounts, holdings, or net worth.
        """
        self._ensure_valid_user_id(user_id)

        self._validate_transaction_data(data)

        self._validate_transaction_ownership_reference(
            portfolio_id=data.portfolio_id,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
        )

        self._validate_transaction_semantics(
            transaction_type=data.transaction_type,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
            asset_id=data.asset_id,
        )

        portfolio = self._resolve_portfolio(
            user_id=user_id,
            portfolio_id=data.portfolio_id,
        )

        source_account = self._resolve_account(
            user_id=user_id,
            account_id=data.source_account_id,
        )

        destination_account = self._resolve_account(
            user_id=user_id,
            account_id=data.destination_account_id,
        )

        asset = self._resolve_asset(
            asset_id=data.asset_id,
        )

        self._validate_resource_activity(
            status=data.status,
            portfolio=portfolio,
            source_account=source_account,
            destination_account=destination_account,
            asset=asset,
        )

        transaction = Transaction(
            portfolio_id=data.portfolio_id,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
            asset_id=data.asset_id,
            transaction_type=data.transaction_type.value,
            status=data.status.value,
            external_reference=data.external_reference,
            amount=data.amount,
            currency=data.currency,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            merchant=data.merchant,
            description=data.description,
            transaction_date=data.transaction_date,
        )

        try:
            self.db.add(transaction)
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "Transaction could not be created because it conflicts "
                "with existing data."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Transaction could not be created."
            ) from exc

        return self.commit(transaction)

    # =====================================================================
    # UPDATE
    # =====================================================================

    def update_transaction(
        self,
        user_id: int,
        transaction_id: int,
        data: TransactionUpdate,
    ) -> Transaction:
        """
        Update a historical transaction under strict financial-history rules.

        COMPLETED transactions are immutable.

        FAILED and CANCELLED transactions may only have descriptive
        metadata corrected:

        - external_reference
        - merchant
        - description

        Financial fields, relationships, transaction type, status, and
        transaction date cannot be changed through the normal update path.
        """
        self._ensure_valid_user_id(user_id)

        transaction = self.require_transaction(
            user_id=user_id,
            transaction_id=transaction_id,
        )

        updates = data.model_dump(exclude_unset=True)

        if not updates:
            return transaction

        if transaction.status == TransactionStatus.COMPLETED.value:
            raise ConflictError(
                "COMPLETED transactions are immutable and cannot be updated."
            )

        self._validate_historical_update_fields(
            updates=updates,
        )

        merged = self._build_merged_transaction_data(
            transaction=transaction,
            updates=updates,
        )

        # TransactionUpdate is intentionally partial. Therefore all
        # semantic validation must happen against the merged final state.
        self._validate_merged_transaction_structure(merged)

        portfolio = self._resolve_portfolio(
            user_id=user_id,
            portfolio_id=merged["portfolio_id"],
        )

        source_account = self._resolve_account(
            user_id=user_id,
            account_id=merged["source_account_id"],
        )

        destination_account = self._resolve_account(
            user_id=user_id,
            account_id=merged["destination_account_id"],
        )

        asset = self._resolve_asset(
            asset_id=merged["asset_id"],
        )

        self._validate_resource_activity(
            status=merged["status"],
            portfolio=portfolio,
            source_account=source_account,
            destination_account=destination_account,
            asset=asset,
        )

        for field_name, value in updates.items():
            setattr(
                transaction,
                field_name,
                self._enum_value(value),
            )

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "Transaction could not be updated because it conflicts "
                "with existing data."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Transaction could not be updated."
            ) from exc

        return self.commit(transaction)

    # =====================================================================
    # STATUS / LIFECYCLE
    # =====================================================================

    def cancel_transaction(
        self,
        user_id: int,
        transaction_id: int,
    ) -> Transaction:
        """
        Cancel a transaction that has not completed.

        COMPLETED and FAILED transactions cannot become CANCELLED.

        Repeating cancellation on an already CANCELLED transaction is
        idempotent.
        """
        transaction = self.require_transaction(
            user_id=user_id,
            transaction_id=transaction_id,
        )

        if transaction.status == TransactionStatus.COMPLETED.value:
            raise ConflictError(
                "COMPLETED transactions cannot be cancelled."
            )

        if transaction.status == TransactionStatus.FAILED.value:
            raise ConflictError(
                "FAILED transactions cannot be cancelled."
            )

        if transaction.status == TransactionStatus.CANCELLED.value:
            return transaction

        transaction.status = TransactionStatus.CANCELLED.value

        return self.commit(transaction)

    def mark_failed(
        self,
        user_id: int,
        transaction_id: int,
    ) -> Transaction:
        """
        Mark an unsuccessful transaction as FAILED.

        COMPLETED and CANCELLED transactions cannot become FAILED.

        Repeating the operation on an already FAILED transaction is
        idempotent.
        """
        transaction = self.require_transaction(
            user_id=user_id,
            transaction_id=transaction_id,
        )

        if transaction.status == TransactionStatus.COMPLETED.value:
            raise ConflictError(
                "COMPLETED transactions cannot be marked as FAILED."
            )

        if transaction.status == TransactionStatus.CANCELLED.value:
            raise ConflictError(
                "CANCELLED transactions cannot be marked as FAILED."
            )

        if transaction.status == TransactionStatus.FAILED.value:
            return transaction

        transaction.status = TransactionStatus.FAILED.value

        return self.commit(transaction)

    # =====================================================================
    # VALIDATION
    # =====================================================================

    @staticmethod
    def _ensure_valid_user_id(user_id: int) -> None:
        """
        Validate the authenticated user's identifier before any lookup.
        """
        if user_id <= 0:
            raise ValidationError(
                "user_id must be greater than zero."
            )

    @staticmethod
    def _validate_transaction_data(
        data: TransactionCreate,
    ) -> None:
        """
        Validate values that should remain protected at the service
        boundary even though Pydantic also validates them.

        Pydantic handles input shape and field-level validation.
        TransactionService enforces domain-level invariants.
        """
        if data.amount <= Decimal("0"):
            raise ValidationError(
                "Transaction amount must be positive."
            )

        if data.status not in {
            TransactionStatus.COMPLETED,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
        }:
            raise ValidationError(
                "Invalid transaction status."
            )

        if data.transaction_type not in {
            TransactionType.BUY,
            TransactionType.SELL,
            TransactionType.DEPOSIT,
            TransactionType.WITHDRAWAL,
            TransactionType.EXPENSE,
            TransactionType.TRANSFER,
            TransactionType.DIVIDEND,
            TransactionType.INTEREST,
            TransactionType.FEE,
        }:
            raise ValidationError(
                "Invalid transaction type."
            )

    @staticmethod
    def _validate_transaction_ownership_reference(
        *,
        portfolio_id: int | None,
        source_account_id: int | None,
        destination_account_id: int | None,
    ) -> None:
        """
        Ensure the transaction has a reliable ownership path.

        Transaction has no user_id, so at least one user-owned resource
        must identify the transaction as belonging to a user.
        """
        if (
            portfolio_id is None
            and source_account_id is None
            and destination_account_id is None
        ):
            raise ValidationError(
                "Transaction must reference a portfolio or account."
            )

    @staticmethod
    def _validate_transaction_semantics(
        *,
        transaction_type: TransactionType,
        source_account_id: int | None,
        destination_account_id: int | None,
        asset_id: int | None,
    ) -> None:
        """
        Enforce Finova's transaction-type semantic requirements.

        Pydantic validates structural relationships such as BUY requiring
        quantity/unit/unit_price. This method validates what each
        transaction type means within Finova.

        No account balances, holdings, or net worth are mutated here.
        """

        # -------------------------------------------------------------
        # BUY / SELL
        # -------------------------------------------------------------

        if transaction_type in {
            TransactionType.BUY,
            TransactionType.SELL,
        }:
            if asset_id is None:
                raise ValidationError(
                    "asset_id is required for BUY and SELL transactions."
                )

            return

        # -------------------------------------------------------------
        # DEPOSIT
        # -------------------------------------------------------------

        if transaction_type == TransactionType.DEPOSIT:
            if destination_account_id is None:
                raise ValidationError(
                    "DEPOSIT transactions require a destination account."
                )

            return

        # -------------------------------------------------------------
        # WITHDRAWAL
        # -------------------------------------------------------------

        if transaction_type == TransactionType.WITHDRAWAL:
            if source_account_id is None:
                raise ValidationError(
                    "WITHDRAWAL transactions require a source account."
                )

            return

        # -------------------------------------------------------------
        # EXPENSE
        # -------------------------------------------------------------

        if transaction_type == TransactionType.EXPENSE:
            if source_account_id is None:
                raise ValidationError(
                    "EXPENSE transactions require a source account."
                )

            return

        # -------------------------------------------------------------
        # TRANSFER
        # -------------------------------------------------------------

        if transaction_type == TransactionType.TRANSFER:
            if (
                source_account_id is None
                or destination_account_id is None
            ):
                raise ValidationError(
                    "TRANSFER transactions require both source and "
                    "destination accounts."
                )

            if source_account_id == destination_account_id:
                raise ValidationError(
                    "TRANSFER source and destination accounts must be different."
                )

            return

        # -------------------------------------------------------------
        # DIVIDEND
        # -------------------------------------------------------------

        if transaction_type == TransactionType.DIVIDEND:
            if asset_id is None:
                raise ValidationError(
                    "DIVIDEND transactions require an asset."
                )

            if destination_account_id is None:
                raise ValidationError(
                    "DIVIDEND transactions require a destination account."
                )

            return

        # -------------------------------------------------------------
        # INTEREST
        # -------------------------------------------------------------

        if transaction_type == TransactionType.INTEREST:
            if destination_account_id is None:
                raise ValidationError(
                    "INTEREST transactions require a destination account."
                )

            return

        # -------------------------------------------------------------
        # FEE
        # -------------------------------------------------------------

        if transaction_type == TransactionType.FEE:
            if source_account_id is None:
                raise ValidationError(
                    "FEE transactions require a source account."
                )

    # =====================================================================
    # RESOURCE RESOLUTION
    # =====================================================================

    def _resolve_portfolio(
        self,
        *,
        user_id: int,
        portfolio_id: int | None,
    ) -> Portfolio | None:
        """
        Resolve a portfolio and verify that it belongs to the user.
        """
        if portfolio_id is None:
            return None

        portfolio = self.db.get(
            Portfolio,
            portfolio_id,
        )

        if portfolio is None:
            raise NotFoundError(
                f"Portfolio {portfolio_id} was not found."
            )

        if portfolio.user_id != user_id:
            # Do not reveal whether another user's resource exists.
            raise NotFoundError(
                f"Portfolio {portfolio_id} was not found."
            )

        return portfolio

    def _resolve_account(
        self,
        *,
        user_id: int,
        account_id: int | None,
    ) -> Account | None:
        """
        Resolve an account and verify that it belongs to the user.
        """
        if account_id is None:
            return None

        account = self.db.get(
            Account,
            account_id,
        )

        if account is None:
            raise NotFoundError(
                f"Account {account_id} was not found."
            )

        if account.user_id != user_id:
            # Do not reveal whether another user's resource exists.
            raise NotFoundError(
                f"Account {account_id} was not found."
            )

        return account

    def _resolve_asset(
        self,
        *,
        asset_id: int | None,
    ) -> Asset | None:
        """
        Resolve a global asset.

        Assets are canonical/global resources and therefore do not require
        user ownership validation.
        """
        if asset_id is None:
            return None

        asset = self.db.get(
            Asset,
            asset_id,
        )

        if asset is None:
            raise NotFoundError(
                f"Asset {asset_id} was not found."
            )

        return asset

    # =====================================================================
    # RESOURCE ACTIVITY
    # =====================================================================

    @staticmethod
    def _validate_resource_activity(
        *,
        status: TransactionStatus | str,
        portfolio: Portfolio | None,
        source_account: Account | None,
        destination_account: Account | None,
        asset: Asset | None,
    ) -> None:
        """
        Prevent COMPLETED transactions from referencing inactive resources.

        FAILED and CANCELLED records are historical and may remain
        associated with resources that later became inactive.
        """
        normalized_status = (
            status.value
            if isinstance(status, TransactionStatus)
            else status
        )

        if normalized_status != TransactionStatus.COMPLETED.value:
            return

        if portfolio is not None and not portfolio.is_active:
            raise ValidationError(
                "Completed transactions cannot use an inactive portfolio."
            )

        if (
            source_account is not None
            and not source_account.is_active
        ):
            raise ValidationError(
                "Completed transactions cannot use an inactive source account."
            )

        if (
            destination_account is not None
            and not destination_account.is_active
        ):
            raise ValidationError(
                "Completed transactions cannot use an inactive "
                "destination account."
            )

        if asset is not None and not asset.is_active:
            raise ValidationError(
                "Completed transactions cannot use an inactive asset."
            )

    # =====================================================================
    # OWNERSHIP
    # =====================================================================

    @staticmethod
    def _transaction_belongs_to_user(
        transaction: Transaction,
        user_id: int,
    ) -> bool:
        """
        Determine ownership using the transaction's user-owned resources.

        All ownership paths are checked independently. This prevents a
        malformed or historical record from becoming accessible merely
        because one relationship is missing.
        """
        if (
            transaction.portfolio is not None
            and transaction.portfolio.user_id == user_id
        ):
            return True

        if (
            transaction.source_account is not None
            and transaction.source_account.user_id == user_id
        ):
            return True

        if (
            transaction.destination_account is not None
            and transaction.destination_account.user_id == user_id
        ):
            return True

        return False

    # =====================================================================
    # HISTORICAL UPDATE VALIDATION
    # =====================================================================

    @staticmethod
    def _validate_historical_update_fields(
        *,
        updates: dict,
    ) -> None:
        """
        Restrict FAILED/CANCELLED updates to descriptive metadata.

        Historical financial meaning and relationship structure cannot be
        rewritten through the normal update endpoint.
        """
        immutable_fields = {
            "portfolio_id",
            "source_account_id",
            "destination_account_id",
            "asset_id",
            "transaction_type",
            "status",
            "amount",
            "currency",
            "quantity",
            "unit",
            "unit_price",
            "transaction_date",
        }

        changed_immutable_fields = immutable_fields.intersection(
            updates.keys()
        )

        if changed_immutable_fields:
            fields = ", ".join(
                sorted(changed_immutable_fields)
            )

            raise ConflictError(
                "Historical transaction financial fields cannot be changed: "
                f"{fields}."
            )

    @staticmethod
    def _build_merged_transaction_data(
        *,
        transaction: Transaction,
        updates: dict,
    ) -> dict:
        """
        Build the complete effective state after a PATCH.

        TransactionUpdate is intentionally partial, so semantic validation
        must operate on the merged existing + updated state.
        """
        fields = (
            "portfolio_id",
            "source_account_id",
            "destination_account_id",
            "asset_id",
            "transaction_type",
            "status",
            "external_reference",
            "amount",
            "currency",
            "quantity",
            "unit",
            "unit_price",
            "merchant",
            "description",
            "transaction_date",
        )

        return {
            field: (
                updates[field]
                if field in updates
                else getattr(transaction, field)
            )
            for field in fields
        }

    @staticmethod
    def _validate_merged_transaction_structure(
        data: dict,
    ) -> None:
        """
        Validate the complete effective transaction state after an update.

        This duplicates only the domain-level validation required after
        merging because TransactionUpdate intentionally does not validate
        a complete transaction.
        """
        TransactionService._validate_transaction_ownership_reference(
            portfolio_id=data["portfolio_id"],
            source_account_id=data["source_account_id"],
            destination_account_id=data["destination_account_id"],
        )

        transaction_type = data["transaction_type"]

        if isinstance(transaction_type, str):
            try:
                transaction_type = TransactionType(
                    transaction_type
                )
            except ValueError as exc:
                raise ValidationError(
                    "Invalid transaction type."
                ) from exc

        # -------------------------------------------------------------
        # BUY / SELL
        # -------------------------------------------------------------

        if transaction_type in {
            TransactionType.BUY,
            TransactionType.SELL,
        }:
            if data["asset_id"] is None:
                raise ValidationError(
                    "asset_id is required for BUY and SELL transactions."
                )

            if data["quantity"] is None:
                raise ValidationError(
                    "quantity is required for BUY and SELL transactions."
                )

            if data["unit_price"] is None:
                raise ValidationError(
                    "unit_price is required for BUY and SELL transactions."
                )

            if data["unit"] is None:
                raise ValidationError(
                    "unit is required for BUY and SELL transactions."
                )

        # -------------------------------------------------------------
        # Quantity / unit / unit price consistency
        # -------------------------------------------------------------

        if (
            data["quantity"] is not None
            and data["unit"] is None
        ):
            raise ValidationError(
                "unit is required when quantity is provided."
            )

        if (
            data["unit"] is not None
            and data["quantity"] is None
        ):
            raise ValidationError(
                "quantity is required when unit is provided."
            )

        if (
            data["unit_price"] is not None
            and data["quantity"] is None
        ):
            raise ValidationError(
                "quantity is required when unit_price is provided."
            )

        # -------------------------------------------------------------
        # Transaction-type semantics
        # -------------------------------------------------------------

        TransactionService._validate_transaction_semantics(
            transaction_type=transaction_type,
            source_account_id=data["source_account_id"],
            destination_account_id=data["destination_account_id"],
            asset_id=data["asset_id"],
        )

    # =====================================================================
    # ENUM PERSISTENCE
    # =====================================================================

    @staticmethod
    def _enum_value(value):
        """
        Convert supported Enum instances to their persisted string values.
        """
        if isinstance(
            value,
            (TransactionType, TransactionStatus),
        ):
            return value.value

        return value
