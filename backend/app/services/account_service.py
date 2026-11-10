from __future__ import annotations

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.exceptions import (
    AuthorizationError,
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.account import Account
from backend.app.models.user import User
from backend.app.schemas.account import (
    AccountCreate,
    AccountSyncUpdate,
    AccountUpdate,
)
from backend.app.services.base_service import BaseService


class AccountService(BaseService[Account]):
    """
    Business/service layer for Finova financial accounts.

    Account represents WHERE a user's funds are held.

    This service is responsible for:

        - ownership-scoped account retrieval
        - account listing
        - account creation
        - user-controlled account updates
        - account activation/deactivation
        - trusted external synchronization
        - domain-level connection-state validation
        - database conflict handling

    This service does NOT:

        - authenticate users
        - validate JWTs
        - hash passwords
        - manage provider credentials
        - calculate net worth
        - calculate investment valuation
        - manage holdings
        - create transactions

    Pydantic schemas are responsible for input validation and
    normalization. This service is responsible for business rules,
    ownership, persistence, and database-level error translation.
    """

    model = Account

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def get_account(
        self,
        user_id: int,
        account_id: int,
    ) -> Account | None:
        """
        Retrieve an account belonging to the specified user.

        Returns None when the account does not exist or belongs
        to another user.

        Ownership is enforced directly in the database query.
        """
        return (
            self.db.query(Account)
            .filter(
                Account.id == account_id,
                Account.user_id == user_id,
            )
            .first()
        )

    def require_account(
        self,
        user_id: int,
        account_id: int,
    ) -> Account:
        """
        Retrieve a user's account or raise NotFoundError.
        """
        account = self.get_account(
            user_id=user_id,
            account_id=account_id,
        )

        if account is None:
            raise NotFoundError(
                f"Account with id {account_id} was not found."
            )

        return account

    def list_accounts(
        self,
        user_id: int,
        *,
        active_only: bool = False,
    ) -> list[Account]:
        """
        Return all accounts belonging to a user.

        Results can optionally be restricted to active accounts.
        """
        query = (
            self.db.query(Account)
            .filter(Account.user_id == user_id)
        )

        if active_only:
            query = query.filter(
                Account.is_active.is_(True)
            )

        return query.order_by(Account.id.asc()).all()

    # =========================================================
    # CREATION
    # =========================================================

    def create_account(
        self,
        user_id: int,
        data: AccountCreate,
    ) -> Account:
        """
        Create a manually maintained account.

        Ownership comes exclusively from user_id.

        Newly created accounts are always:

            is_connected = False
            provider = None
            external_account_id = None
            last_synced_at = None

        External synchronization fields cannot be supplied through
        AccountCreate.
        """
        self._ensure_active_user(user_id)

        account = Account(
            user_id=user_id,
            name=data.name,
            account_type=data.account_type,
            institution_name=data.institution_name,
            currency=data.currency,
            balance=data.balance,
            is_connected=False,
            provider=None,
            external_account_id=None,
            is_active=True,
            last_synced_at=None,
        )

        self.add(account)

        try:
            self.flush()
        except IntegrityError as exc:
            self.rollback()

            raise ConflictError(
                "Unable to create account because it conflicts "
                "with an existing database constraint."
            ) from exc
        except SQLAlchemyError as exc:
            self.rollback()

            raise FinovaError(
                "Unable to create account."
            ) from exc

        self.commit(account)

        return account

    # =========================================================
    # USER-FACING UPDATE
    # =========================================================

    def update_account(
        self,
        user_id: int,
        account_id: int,
        data: AccountUpdate,
    ) -> Account:
        """
        Update user-controlled account fields.

        Synchronization fields are deliberately unavailable here.

        Supported fields:

            - name
            - account_type
            - institution_name
            - currency
            - balance
            - is_active
        """
        account = self.require_account(
            user_id=user_id,
            account_id=account_id,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return account

        for field, value in update_data.items():
            setattr(account, field, value)

        try:
            self.flush()
        except IntegrityError as exc:
            self.rollback()

            raise ConflictError(
                "Unable to update account because it conflicts "
                "with an existing database constraint."
            ) from exc
        except SQLAlchemyError as exc:
            self.rollback()

            raise FinovaError(
                "Unable to update account."
            ) from exc

        self.commit(account)

        return account

    # =========================================================
    # ACCOUNT STATUS
    # =========================================================

    def deactivate_account(
        self,
        user_id: int,
        account_id: int,
    ) -> Account:
        """
        Deactivate an account without deleting it.

        Deactivation preserves financial history.

        The operation is idempotent.
        """
        account = self.require_account(
            user_id=user_id,
            account_id=account_id,
        )

        if not account.is_active:
            return account

        account.is_active = False

        self.commit(account)

        return account

    def activate_account(
        self,
        user_id: int,
        account_id: int,
    ) -> Account:
        """
        Reactivate a previously deactivated account.

        The operation is idempotent.
        """
        account = self.require_account(
            user_id=user_id,
            account_id=account_id,
        )

        if account.is_active:
            return account

        account.is_active = True

        self.commit(account)

        return account

    # =========================================================
    # TRUSTED SYNCHRONIZATION
    # =========================================================

    def sync_account(
        self,
        account_id: int,
        data: AccountSyncUpdate,
    ) -> Account:
        """
        Update an account using trusted synchronization data.

        This method must only be called by trusted backend
        synchronization infrastructure.

        Synchronization may update:

            - balance
            - is_connected
            - provider
            - external_account_id
            - last_synced_at
        """
        account = self.get_by_id(account_id)

        if account is None:
            raise NotFoundError(
                f"Account with id {account_id} was not found."
            )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return account

        # Construct the complete resulting connection state before
        # modifying the SQLAlchemy object.
        new_is_connected = (
            update_data.get(
                "is_connected",
                account.is_connected,
            )
        )

        new_provider = update_data.get(
            "provider",
            account.provider,
        )

        new_external_account_id = update_data.get(
            "external_account_id",
            account.external_account_id,
        )

        self._validate_connection_state(
            is_connected=new_is_connected,
            provider=new_provider,
            external_account_id=new_external_account_id,
        )

        for field, value in update_data.items():
            setattr(account, field, value)

        try:
            self.flush()
        except IntegrityError as exc:
            self.rollback()

            raise ConflictError(
                "The external account is already linked "
                "to another Finova account."
            ) from exc
        except SQLAlchemyError as exc:
            self.rollback()

            raise FinovaError(
                "Unable to synchronize account."
            ) from exc

        self.commit(account)

        return account

    # =========================================================
    # USER VALIDATION
    # =========================================================

    def _ensure_active_user(
        self,
        user_id: int,
    ) -> User:
        """
        Verify that the owning user exists and is active.

        Account creation is not permitted for inactive users.
        """
        user = self.db.get(User, user_id)

        if user is None:
            raise NotFoundError(
                f"User with id {user_id} was not found."
            )

        if not user.is_active:
            raise AuthorizationError(
                "Inactive users cannot create accounts."
            )

        return user

    # =========================================================
    # SYNCHRONIZATION VALIDATION
    # =========================================================

    @staticmethod
    def _validate_connection_state(
        *,
        is_connected: bool,
        provider: str | None,
        external_account_id: str | None,
    ) -> None:
        """
        Validate the complete external connection state.

        Connected accounts require:

            provider
            external_account_id

        Disconnected accounts must not retain either identifier.
        """
        if is_connected:
            if not provider:
                raise ValidationError(
                    "A connected account must have a provider."
                )

            if not external_account_id:
                raise ValidationError(
                    "A connected account must have an external "
                    "account ID."
                )

            return

        if provider is not None:
            raise ValidationError(
                "A disconnected account cannot have a provider."
            )

        if external_account_id is not None:
            raise ValidationError(
                "A disconnected account cannot have an external "
                "account ID."
            )