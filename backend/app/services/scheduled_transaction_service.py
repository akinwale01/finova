from __future__ import annotations

import calendar
from datetime import datetime, timedelta

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
from backend.app.models.scheduled_transaction import (
    RecurrenceType,
    ScheduledTransaction,
    ScheduledTransactionExecutionMode,
    ScheduledTransactionStatus,
    ScheduledTransactionType,
)
from backend.app.schemas.scheduled_transaction import (
    ScheduledTransactionCreate,
    ScheduledTransactionUpdate,
)
from backend.app.services.base_service import BaseService


class ScheduledTransactionService(BaseService[ScheduledTransaction]):
    """
    Service responsible for scheduled-transaction lifecycle management.

    A ScheduledTransaction represents a future financial intent.

    This service:
        - validates ownership,
        - validates referenced resources,
        - creates and updates schedules,
        - manages lifecycle transitions,
        - manages recurrence bookkeeping,
        - protects execution state.

    This service does NOT execute financial transactions.

    Actual execution must eventually create a normal Transaction and then
    update this schedule's execution state.
    """

    model = ScheduledTransaction

    def __init__(self, db: Session):
        super().__init__(db)

    # ======================================================================
    # Retrieval
    # ======================================================================

    def get_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
    ) -> ScheduledTransaction | None:
        self._ensure_valid_user_id(user_id)

        scheduled_transaction = self.get_by_id(scheduled_transaction_id)

        if scheduled_transaction is None:
            return None

        if scheduled_transaction.user_id != user_id:
            return None

        return scheduled_transaction

    def require_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.get_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        if scheduled_transaction is None:
            raise NotFoundError(
                f"Scheduled transaction "
                f"{scheduled_transaction_id} was not found."
            )

        return scheduled_transaction

    def list_scheduled_transactions(
        self,
        user_id: int,
        *,
        portfolio_id: int | None = None,
        account_id: int | None = None,
        asset_id: int | None = None,
        scheduled_type: ScheduledTransactionType | None = None,
        status: ScheduledTransactionStatus | None = None,
        is_recurring: bool | None = None,
    ) -> list[ScheduledTransaction]:
        self._ensure_valid_user_id(user_id)

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

        if asset_id is not None:
            self._resolve_asset(asset_id)

        statement = (
            select(ScheduledTransaction)
            .where(ScheduledTransaction.user_id == user_id)
            .order_by(
                ScheduledTransaction.scheduled_date.asc(),
                ScheduledTransaction.id.asc(),
            )
        )

        if portfolio_id is not None:
            statement = statement.where(
                ScheduledTransaction.portfolio_id == portfolio_id
            )

        if account_id is not None:
            statement = statement.where(
                (ScheduledTransaction.source_account_id == account_id)
                | (
                    ScheduledTransaction.destination_account_id
                    == account_id
                )
            )

        if asset_id is not None:
            statement = statement.where(
                ScheduledTransaction.asset_id == asset_id
            )

        if scheduled_type is not None:
            statement = statement.where(
                ScheduledTransaction.scheduled_type
                == scheduled_type.value
            )

        if status is not None:
            statement = statement.where(
                ScheduledTransaction.status == status.value
            )

        if is_recurring is not None:
            statement = statement.where(
                ScheduledTransaction.is_recurring == is_recurring
            )

        return list(self.db.scalars(statement).all())

    # ======================================================================
    # Creation
    # ======================================================================

    def create_scheduled_transaction(
        self,
        user_id: int,
        data: ScheduledTransactionCreate,
    ) -> ScheduledTransaction:
        self._ensure_valid_user_id(user_id)

        self._validate_create_data(data)

        self._validate_ownership_references(
            user_id=user_id,
            portfolio_id=data.portfolio_id,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
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

        asset = self._resolve_asset(data.asset_id)

        self._validate_resource_activity(
            portfolio=portfolio,
            source_account=source_account,
            destination_account=destination_account,
            asset=asset,
        )

        scheduled_transaction = ScheduledTransaction(
            user_id=user_id,
            portfolio_id=data.portfolio_id,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
            asset_id=data.asset_id,
            scheduled_type=self._enum_value(data.scheduled_type),
            execution_mode=self._enum_value(data.execution_mode),
            status=ScheduledTransactionStatus.SCHEDULED.value,
            is_recurring=data.is_recurring,
            recurrence=self._enum_value(data.recurrence),
            recurrence_end_date=data.recurrence_end_date,
            recurrence_count=data.recurrence_count,
            execution_count=0,
            amount=data.amount,
            currency=data.currency,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            merchant=data.merchant,
            external_reference=data.external_reference,
            description=data.description,
            scheduled_date=data.scheduled_date,
        )

        try:
            self.db.add(scheduled_transaction)
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "Scheduled transaction could not be created "
                "because it conflicts with existing data."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Scheduled transaction could not be created."
            ) from exc

        return self.commit(scheduled_transaction)

    # ======================================================================
    # Update
    # ======================================================================

    def update_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
        data: ScheduledTransactionUpdate,
    ) -> ScheduledTransaction:
        self._ensure_valid_user_id(user_id)

        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        updates = data.model_dump(exclude_unset=True)

        if not updates:
            return scheduled_transaction

        self._validate_update_allowed_state(scheduled_transaction)

        merged = self._build_merged_data(
            scheduled_transaction=scheduled_transaction,
            updates=updates,
        )

        self._validate_merged_data(merged)

        self._validate_ownership_references(
            user_id=user_id,
            portfolio_id=merged["portfolio_id"],
            source_account_id=merged["source_account_id"],
            destination_account_id=merged["destination_account_id"],
        )

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

        asset = self._resolve_asset(merged["asset_id"])

        self._validate_resource_activity(
            portfolio=portfolio,
            source_account=source_account,
            destination_account=destination_account,
            asset=asset,
        )

        for field_name, value in updates.items():
            setattr(
                scheduled_transaction,
                field_name,
                self._enum_value(value),
            )

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "Scheduled transaction could not be updated "
                "because it conflicts with existing data."
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise FinovaError(
                "Scheduled transaction could not be updated."
            ) from exc

        return self.commit(scheduled_transaction)

    # ======================================================================
    # Cancellation
    # ======================================================================

    def cancel_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        status = scheduled_transaction.status

        if status == ScheduledTransactionStatus.CANCELLED.value:
            return scheduled_transaction

        if status == ScheduledTransactionStatus.COMPLETED.value:
            raise ConflictError(
                "COMPLETED scheduled transactions cannot be cancelled."
            )

        if status == ScheduledTransactionStatus.PROCESSING.value:
            raise ConflictError(
                "PROCESSING scheduled transactions cannot be cancelled."
            )

        scheduled_transaction.status = (
            ScheduledTransactionStatus.CANCELLED.value
        )

        return self.commit(scheduled_transaction)

    # ======================================================================
    # Pause / Resume
    # ======================================================================

    def pause_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        status = scheduled_transaction.status

        if status == ScheduledTransactionStatus.PAUSED.value:
            return scheduled_transaction

        if status != ScheduledTransactionStatus.SCHEDULED.value:
            raise ConflictError(
                "Only SCHEDULED transactions can be paused."
            )

        if not scheduled_transaction.is_recurring:
            raise ConflictError(
                "Only recurring scheduled transactions can be paused."
            )

        scheduled_transaction.status = (
            ScheduledTransactionStatus.PAUSED.value
        )

        return self.commit(scheduled_transaction)

    def resume_scheduled_transaction(
        self,
        user_id: int,
        scheduled_transaction_id: int,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        status = scheduled_transaction.status

        if status == ScheduledTransactionStatus.SCHEDULED.value:
            return scheduled_transaction

        if status != ScheduledTransactionStatus.PAUSED.value:
            raise ConflictError(
                "Only PAUSED scheduled transactions can be resumed."
            )

        scheduled_transaction.status = (
            ScheduledTransactionStatus.SCHEDULED.value
        )

        return self.commit(scheduled_transaction)

    # ======================================================================
    # Execution lifecycle
    # ======================================================================

    def mark_processing(
        self,
        user_id: int,
        scheduled_transaction_id: int,
        *,
        attempt_at: datetime | None = None,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        if scheduled_transaction.status not in {
            ScheduledTransactionStatus.SCHEDULED.value,
            ScheduledTransactionStatus.FAILED.value,
        }:
            raise ConflictError(
                "Only SCHEDULED or FAILED scheduled transactions "
                "can enter PROCESSING."
            )

        scheduled_transaction.status = (
            ScheduledTransactionStatus.PROCESSING.value
        )
        scheduled_transaction.last_attempt_at = (
            attempt_at or datetime.now(scheduled_transaction.scheduled_date.tzinfo)
        )
        scheduled_transaction.execution_error = None

        return self.commit(scheduled_transaction)

    def mark_failed(
        self,
        user_id: int,
        scheduled_transaction_id: int,
        *,
        error: str,
        attempt_at: datetime | None = None,
    ) -> ScheduledTransaction:
        if not error or not error.strip():
            raise ValidationError(
                "An execution error is required when marking "
                "a scheduled transaction as FAILED."
            )

        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        if scheduled_transaction.status != (
            ScheduledTransactionStatus.PROCESSING.value
        ):
            raise ConflictError(
                "Only PROCESSING scheduled transactions "
                "can be marked as FAILED."
            )

        scheduled_transaction.status = (
            ScheduledTransactionStatus.FAILED.value
        )
        scheduled_transaction.last_attempt_at = (
            attempt_at or datetime.now(scheduled_transaction.scheduled_date.tzinfo)
        )
        scheduled_transaction.execution_error = error.strip()

        return self.commit(scheduled_transaction)

    def mark_completed(
        self,
        user_id: int,
        scheduled_transaction_id: int,
        *,
        executed_at: datetime | None = None,
    ) -> ScheduledTransaction:
        scheduled_transaction = self.require_scheduled_transaction(
            user_id=user_id,
            scheduled_transaction_id=scheduled_transaction_id,
        )

        if scheduled_transaction.status != (
            ScheduledTransactionStatus.PROCESSING.value
        ):
            raise ConflictError(
                "Only PROCESSING scheduled transactions "
                "can be marked as COMPLETED."
            )

        completion_time = executed_at or datetime.now(
            scheduled_transaction.scheduled_date.tzinfo
        )

        scheduled_transaction.execution_count += 1
        scheduled_transaction.executed_at = completion_time
        scheduled_transaction.last_attempt_at = completion_time
        scheduled_transaction.execution_error = None

        if self._has_remaining_recurrence(scheduled_transaction):
            next_date = self._calculate_next_occurrence(
                scheduled_transaction
            )

            if self._occurrence_is_allowed(
                scheduled_transaction,
                next_date,
            ):
                scheduled_transaction.scheduled_date = next_date
                scheduled_transaction.status = (
                    ScheduledTransactionStatus.SCHEDULED.value
                )
            else:
                scheduled_transaction.status = (
                    ScheduledTransactionStatus.COMPLETED.value
                )
        else:
            scheduled_transaction.status = (
                ScheduledTransactionStatus.COMPLETED.value
            )

        return self.commit(scheduled_transaction)

    # ======================================================================
    # Validation
    # ======================================================================

    @staticmethod
    def _ensure_valid_user_id(user_id: int) -> None:
        if user_id <= 0:
            raise ValidationError(
                "user_id must be greater than zero."
            )

    @staticmethod
    def _validate_create_data(
        data: ScheduledTransactionCreate,
    ) -> None:
        if data.scheduled_date is None:
            raise ValidationError(
                "scheduled_date is required."
            )

    @staticmethod
    def _validate_ownership_references(
        *,
        user_id: int,
        portfolio_id: int | None,
        source_account_id: int | None,
        destination_account_id: int | None,
    ) -> None:
        if (
            portfolio_id is None
            and source_account_id is None
            and destination_account_id is None
        ):
            raise ValidationError(
                "Scheduled transaction must reference "
                "a portfolio or account."
            )

    @staticmethod
    def _validate_update_allowed_state(
        scheduled_transaction: ScheduledTransaction,
    ) -> None:
        if scheduled_transaction.status in {
            ScheduledTransactionStatus.PROCESSING.value,
            ScheduledTransactionStatus.COMPLETED.value,
        }:
            raise ConflictError(
                f"{scheduled_transaction.status} scheduled transactions "
                "cannot be modified."
            )

        if scheduled_transaction.status == (
            ScheduledTransactionStatus.CANCELLED.value
        ):
            raise ConflictError(
                "CANCELLED scheduled transactions cannot be modified."
            )

    @staticmethod
    def _build_merged_data(
        *,
        scheduled_transaction: ScheduledTransaction,
        updates: dict,
    ) -> dict:
        fields = (
            "portfolio_id",
            "source_account_id",
            "destination_account_id",
            "asset_id",
            "scheduled_type",
            "execution_mode",
            "amount",
            "currency",
            "quantity",
            "unit",
            "unit_price",
            "merchant",
            "external_reference",
            "description",
            "scheduled_date",
            "is_recurring",
            "recurrence",
            "recurrence_end_date",
            "recurrence_count",
        )

        merged = {
            field_name: getattr(
                scheduled_transaction,
                field_name,
            )
            for field_name in fields
        }

        merged.update(updates)

        return merged

    @staticmethod
    def _validate_merged_data(data: dict) -> None:
        scheduled_type = ScheduledTransactionType(
        data["scheduled_type"]
        )
        execution_mode = ScheduledTransactionExecutionMode(
            data["execution_mode"]
        )

        amount = data["amount"]
        quantity = data["quantity"]
        unit = data["unit"]
        unit_price = data["unit_price"]
        asset_id = data["asset_id"]

        if execution_mode == ScheduledTransactionExecutionMode.AMOUNT:
            if amount is None:
                raise ValidationError(
                    "amount is required when execution_mode is AMOUNT."
                )
            if quantity is not None:
                raise ValidationError(
                    "quantity must be omitted when execution_mode is AMOUNT."
                )

        elif execution_mode == ScheduledTransactionExecutionMode.QUANTITY:
            if quantity is None:
                raise ValidationError(
                    "quantity is required when execution_mode is QUANTITY."
                )
            if amount is not None:
                raise ValidationError(
                    "amount must be omitted when execution_mode is QUANTITY."
                )

        elif execution_mode == ScheduledTransactionExecutionMode.BOTH:
            if amount is None or quantity is None:
                raise ValidationError(
                    "BOTH execution mode requires both amount and quantity."
                )

        if scheduled_type in {
            ScheduledTransactionType.BUY,
            ScheduledTransactionType.SELL,
        }:
            if asset_id is None:
                raise ValidationError(
                    "asset_id is required for BUY and SELL schedules."
                )

        if any(
            value is not None
            for value in (quantity, unit, unit_price)
        ) and asset_id is None:
            raise ValidationError(
                "Asset quantity information requires asset_id."
            )

        source_account_id = data["source_account_id"]
        destination_account_id = data["destination_account_id"]

        if scheduled_type == ScheduledTransactionType.TRANSFER:
            if source_account_id is None:
                raise ValidationError(
                    "source_account_id is required for TRANSFER."
                )
            if destination_account_id is None:
                raise ValidationError(
                    "destination_account_id is required for TRANSFER."
                )
            if source_account_id == destination_account_id:
                raise ValidationError(
                    "source_account_id and destination_account_id "
                    "must be different."
                )

        elif scheduled_type == ScheduledTransactionType.DEPOSIT:
            if destination_account_id is None:
                raise ValidationError(
                    "destination_account_id is required for DEPOSIT."
                )

        elif scheduled_type in {
            ScheduledTransactionType.WITHDRAWAL,
            ScheduledTransactionType.EXPENSE,
            ScheduledTransactionType.FEE,
        }:
            if source_account_id is None:
                raise ValidationError(
                    f"source_account_id is required for "
                    f"{scheduled_type.value}."
                )

        elif scheduled_type == ScheduledTransactionType.BUY:
            if source_account_id is None:
                raise ValidationError(
                    "source_account_id is required for BUY."
                )

        elif scheduled_type == ScheduledTransactionType.SELL:
            if destination_account_id is None:
                raise ValidationError(
                    "destination_account_id is required for SELL."
                )

        elif scheduled_type in {
            ScheduledTransactionType.DIVIDEND,
            ScheduledTransactionType.INTEREST,
        }:
            if destination_account_id is None:
                raise ValidationError(
                    f"destination_account_id is required for "
                    f"{scheduled_type.value}."
                )

        is_recurring = data["is_recurring"]
        recurrence = data["recurrence"]
        recurrence_end_date = data["recurrence_end_date"]
        recurrence_count = data["recurrence_count"]
        scheduled_date = data["scheduled_date"]

        if is_recurring:
            if recurrence is None:
                raise ValidationError(
                    "recurrence is required when is_recurring is True."
                )
        else:
            if recurrence is not None:
                raise ValidationError(
                    "recurrence must be None when is_recurring is False."
                )
            if recurrence_end_date is not None:
                raise ValidationError(
                    "recurrence_end_date requires "
                    "is_recurring to be True."
                )
            if recurrence_count is not None:
                raise ValidationError(
                    "recurrence_count requires "
                    "is_recurring to be True."
                )

        if (
            recurrence_end_date is not None
            and recurrence_end_date <= scheduled_date
        ):
            raise ValidationError(
                "recurrence_end_date must be later than scheduled_date."
            )

        if amount is not None and amount <= 0:
            raise ValidationError("amount must be positive.")

        if quantity is not None and quantity <= 0:
            raise ValidationError("quantity must be positive.")

        if unit_price is not None and unit_price <= 0:
            raise ValidationError("unit_price must be positive.")

        currency = data["currency"]

        if (
            not isinstance(currency, str)
            or len(currency) != 3
            or not currency.isalpha()
        ):
            raise ValidationError(
                "Currency must contain exactly three letters."
            )

    # ======================================================================
    # Resource resolution
    # ======================================================================

    def _resolve_portfolio(
        self,
        *,
        user_id: int,
        portfolio_id: int | None,
    ) -> Portfolio | None:
        if portfolio_id is None:
            return None

        portfolio = self.db.scalar(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == user_id,
            )
        )

        if portfolio is None:
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
        if account_id is None:
            return None

        account = self.db.scalar(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == user_id,
            )
        )

        if account is None:
            raise NotFoundError(
                f"Account {account_id} was not found."
            )

        return account

    def _resolve_asset(
        self,
        asset_id: int | None,
    ) -> Asset | None:
        if asset_id is None:
            return None

        asset = self.db.scalar(
            select(Asset).where(Asset.id == asset_id)
        )

        if asset is None:
            raise NotFoundError(
                f"Asset {asset_id} was not found."
            )

        return asset

    @staticmethod
    def _validate_resource_activity(
        *,
        portfolio: Portfolio | None,
        source_account: Account | None,
        destination_account: Account | None,
        asset: Asset | None,
    ) -> None:
        if portfolio is not None and not portfolio.is_active:
            raise ConflictError(
                "Scheduled transaction cannot reference "
                "an inactive portfolio."
            )

        if source_account is not None and not source_account.is_active:
            raise ConflictError(
                "Scheduled transaction cannot reference "
                "an inactive source account."
            )

        if (
            destination_account is not None
            and not destination_account.is_active
        ):
            raise ConflictError(
                "Scheduled transaction cannot reference "
                "an inactive destination account."
            )

        if asset is not None and not asset.is_active:
            raise ConflictError(
                "Scheduled transaction cannot reference "
                "an inactive asset."
            )

    # ======================================================================
    # Recurrence
    # ======================================================================

    @staticmethod
    def _has_remaining_recurrence(
        scheduled_transaction: ScheduledTransaction,
    ) -> bool:
        if not scheduled_transaction.is_recurring:
            return False

        if (
            scheduled_transaction.recurrence_count is not None
            and scheduled_transaction.execution_count
            >= scheduled_transaction.recurrence_count
        ):
            return False

        return True

    @staticmethod
    def _calculate_next_occurrence(
        scheduled_transaction: ScheduledTransaction,
    ) -> datetime:
        current = scheduled_transaction.scheduled_date
        recurrence = RecurrenceType(
            scheduled_transaction.recurrence
        )

        if recurrence == RecurrenceType.DAILY:
            return current + timedelta(days=1)

        if recurrence == RecurrenceType.WEEKLY:
            return current + timedelta(weeks=1)

        if recurrence == RecurrenceType.MONTHLY:
            return ScheduledTransactionService._add_months(
                current,
                1,
            )

        if recurrence == RecurrenceType.YEARLY:
            return ScheduledTransactionService._add_years(
                current,
                1,
            )

        raise ValidationError(
            f"Unsupported recurrence type: {scheduled_transaction.recurrence}"
        )

    @staticmethod
    def _add_months(
        value: datetime,
        months: int,
    ) -> datetime:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1

        day = min(
            value.day,
            calendar.monthrange(year, month)[1],
        )

        return value.replace(
            year=year,
            month=month,
            day=day,
        )

    @staticmethod
    def _add_years(
        value: datetime,
        years: int,
    ) -> datetime:
        year = value.year + years
        day = min(
            value.day,
            calendar.monthrange(year, value.month)[1],
        )

        return value.replace(
            year=year,
            day=day,
        )

    @staticmethod
    def _occurrence_is_allowed(
        scheduled_transaction: ScheduledTransaction,
        next_date: datetime,
    ) -> bool:
        if (
            scheduled_transaction.recurrence_end_date is not None
            and next_date > scheduled_transaction.recurrence_end_date
        ):
            return False

        if (
            scheduled_transaction.recurrence_count is not None
            and scheduled_transaction.execution_count
            >= scheduled_transaction.recurrence_count
        ):
            return False

        return True

    @staticmethod
    def _enum_value(value):
        return value.value if hasattr(value, "value") else value