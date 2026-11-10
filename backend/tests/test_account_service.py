"""
PostgreSQL integration tests for AccountService.

Run with:

    pytest -q tests/test_account_service.py

These tests use the application's configured PostgreSQL database.

IMPORTANT:
    Do NOT replace the database with SQLite.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.account import Account
from backend.app.models.user import User
from backend.app.schemas.account import (
    AccountCreate,
    AccountSyncUpdate,
    AccountType,
    AccountUpdate,
)
from backend.app.services.account_service import AccountService


# =============================================================
# TEST DATA HELPERS
# =============================================================

def create_test_user(
    db: Session,
    *,
    email: str,
    is_active: bool = True,
) -> User:
    """
    Create a valid test user directly in PostgreSQL.

    The finalized User model requires password_hash, so the test
    fixture must provide a valid non-null value. Authentication is
    not being tested here, therefore a deterministic test hash is
    sufficient.
    """
    user = User(
        email=email,
        password_hash="test-password-hash",
        is_active=is_active,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_test_account(
    db: Session,
    *,
    user_id: int,
    name: str = "Test Account",
    currency: str = "NGN",
    balance: Decimal = Decimal("100000.00"),
    account_type: AccountType = AccountType.BANK,
    is_active: bool = True,
    is_connected: bool = False,
    provider: str | None = None,
    external_account_id: str | None = None,
) -> Account:
    """
    Create an Account directly for tests that need a pre-existing
    account.
    """
    account = Account(
        user_id=user_id,
        name=name,
        account_type=account_type,
        institution_name=None,
        currency=currency,
        balance=balance,
        is_connected=is_connected,
        provider=provider,
        external_account_id=external_account_id,
        is_active=is_active,
        last_synced_at=None,
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return account


# =============================================================
# FIXTURES
# =============================================================

@pytest.fixture
def test_user(db: Session) -> User:
    """
    Create an active test user.
    """
    return create_test_user(
        db,
        email="account-service-test@example.com",
    )


@pytest.fixture
def second_test_user(db: Session) -> User:
    """
    Create a second active test user for ownership tests.
    """
    return create_test_user(
        db,
        email="account-service-owner-two@example.com",
    )


@pytest.fixture
def inactive_test_user(db: Session) -> User:
    """
    Create an inactive test user.
    """
    return create_test_user(
        db,
        email="account-service-inactive@example.com",
        is_active=False,
    )


@pytest.fixture
def service(db: Session) -> AccountService:
    """
    Provide AccountService using the PostgreSQL test session.
    """
    return AccountService(db)


# =============================================================
# CREATION
# =============================================================

def test_create_account(
    service: AccountService,
    test_user: User,
) -> None:
    """
    An active user can create a manual account.
    """
    data = AccountCreate(
        name="Main Bank Account",
        account_type=AccountType.BANK,
        institution_name="GTBank",
        currency="ngn",
        balance=Decimal("250000.50"),
    )

    account = service.create_account(
        user_id=test_user.id,
        data=data,
    )

    assert account.id is not None
    assert account.user_id == test_user.id
    assert account.name == "Main Bank Account"
    assert account.account_type == AccountType.BANK
    assert account.institution_name == "GTBank"
    assert account.currency == "NGN"
    assert account.balance == Decimal("250000.500000000000")
    assert account.is_connected is False
    assert account.provider is None
    assert account.external_account_id is None
    assert account.is_active is True
    assert account.last_synced_at is None


def test_create_account_defaults_balance_to_zero(
    service: AccountService,
    test_user: User,
) -> None:
    """
    AccountCreate defaults the initial balance to zero.
    """
    data = AccountCreate(
        name="Cash Wallet",
        account_type=AccountType.CASH,
        currency="NGN",
    )

    account = service.create_account(
        user_id=test_user.id,
        data=data,
    )

    assert account.balance == Decimal("0")


def test_create_account_allows_negative_balance(
    service: AccountService,
    test_user: User,
) -> None:
    """
    Negative balances are valid because the Account model explicitly
    supports overdrafts and other legitimate negative positions.
    """
    data = AccountCreate(
        name="Overdraft Account",
        account_type=AccountType.BANK,
        currency="NGN",
        balance=Decimal("-50000.25"),
    )

    account = service.create_account(
        user_id=test_user.id,
        data=data,
    )

    assert account.balance == Decimal("-50000.250000000000")


def test_create_account_with_all_supported_account_types(
    service: AccountService,
    test_user: User,
) -> None:
    """
    Every AccountType supported by the schema/model can be persisted.
    """
    for index, account_type in enumerate(AccountType):
        data = AccountCreate(
            name=f"Account Type {index}",
            account_type=account_type,
            currency="USD",
            balance=Decimal("100.00"),
        )

        account = service.create_account(
            user_id=test_user.id,
            data=data,
        )

        assert account.account_type == account_type


def test_create_account_for_missing_user(
    service: AccountService,
) -> None:
    """
    Account creation fails when the owning user does not exist.
    """
    data = AccountCreate(
        name="Missing User Account",
        account_type=AccountType.BANK,
        currency="NGN",
    )

    with pytest.raises(NotFoundError):
        service.create_account(
            user_id=999999999,
            data=data,
        )


def test_create_account_for_inactive_user(
    service: AccountService,
    inactive_test_user: User,
) -> None:
    """
    Inactive users cannot create accounts.
    """
    data = AccountCreate(
        name="Inactive User Account",
        account_type=AccountType.BANK,
        currency="NGN",
    )

    with pytest.raises(AuthorizationError):
        service.create_account(
            user_id=inactive_test_user.id,
            data=data,
        )


# =============================================================
# RETRIEVAL
# =============================================================

def test_get_account_returns_owned_account(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A user can retrieve their own account.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    result = service.get_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result is not None
    assert result.id == account.id
    assert result.user_id == test_user.id


def test_get_account_returns_none_for_other_users_account(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    A user cannot discover another user's account through
    ownership-scoped retrieval.
    """
    account = create_test_account(
        db,
        user_id=second_test_user.id,
    )

    result = service.get_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result is None


def test_get_account_returns_none_for_missing_account(
    service: AccountService,
    test_user: User,
) -> None:
    """
    Missing accounts return None from get_account().
    """
    result = service.get_account(
        user_id=test_user.id,
        account_id=999999999,
    )

    assert result is None


def test_require_account_returns_owned_account(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    require_account returns an existing owned account.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    result = service.require_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result.id == account.id


def test_require_account_raises_for_missing_account(
    service: AccountService,
    test_user: User,
) -> None:
    """
    require_account raises NotFoundError for a missing account.
    """
    with pytest.raises(NotFoundError):
        service.require_account(
            user_id=test_user.id,
            account_id=999999999,
        )


def test_require_account_raises_for_other_users_account(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    require_account does not expose another user's account.
    """
    account = create_test_account(
        db,
        user_id=second_test_user.id,
    )

    with pytest.raises(NotFoundError):
        service.require_account(
            user_id=test_user.id,
            account_id=account.id,
        )


# =============================================================
# LISTING
# =============================================================

def test_list_accounts_returns_only_owned_accounts(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    list_accounts never returns another user's accounts.
    """
    owned_one = create_test_account(
        db,
        user_id=test_user.id,
        name="Owned One",
    )

    owned_two = create_test_account(
        db,
        user_id=test_user.id,
        name="Owned Two",
    )

    other = create_test_account(
        db,
        user_id=second_test_user.id,
        name="Other User",
    )

    accounts = service.list_accounts(
        user_id=test_user.id,
    )

    account_ids = {account.id for account in accounts}

    assert owned_one.id in account_ids
    assert owned_two.id in account_ids
    assert other.id not in account_ids


def test_list_accounts_active_only(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    active_only=True excludes inactive accounts.
    """
    active_account = create_test_account(
        db,
        user_id=test_user.id,
        name="Active Account",
        is_active=True,
    )

    inactive_account = create_test_account(
        db,
        user_id=test_user.id,
        name="Inactive Account",
        is_active=False,
    )

    accounts = service.list_accounts(
        user_id=test_user.id,
        active_only=True,
    )

    account_ids = {account.id for account in accounts}

    assert active_account.id in account_ids
    assert inactive_account.id not in account_ids


def test_list_accounts_returns_inactive_when_active_only_false(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    active_only=False returns both active and inactive accounts.
    """
    active_account = create_test_account(
        db,
        user_id=test_user.id,
        name="Active Account",
        is_active=True,
    )

    inactive_account = create_test_account(
        db,
        user_id=test_user.id,
        name="Inactive Account",
        is_active=False,
    )

    accounts = service.list_accounts(
        user_id=test_user.id,
        active_only=False,
    )

    account_ids = {account.id for account in accounts}

    assert active_account.id in account_ids
    assert inactive_account.id in account_ids


# =============================================================
# UPDATE
# =============================================================

def test_update_account_name(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Users can update the account name.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountUpdate(
        name="Updated Account Name",
    )

    updated = service.update_account(
        user_id=test_user.id,
        account_id=account.id,
        data=data,
    )

    assert updated.name == "Updated Account Name"


def test_update_account_multiple_fields(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Multiple user-controlled fields can be updated together.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountUpdate(
        name="Updated Bank",
        account_type=AccountType.BROKERAGE,
        institution_name="New Institution",
        currency="USD",
        balance=Decimal("75000.25"),
    )

    updated = service.update_account(
        user_id=test_user.id,
        account_id=account.id,
        data=data,
    )

    assert updated.name == "Updated Bank"
    assert updated.account_type == AccountType.BROKERAGE
    assert updated.institution_name == "New Institution"
    assert updated.currency == "USD"
    assert updated.balance == Decimal("75000.250000000000")


def test_update_account_preserves_unspecified_fields(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    PATCH-style updates change only supplied fields.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        name="Original Name",
        currency="NGN",
        balance=Decimal("5000.00"),
    )

    data = AccountUpdate(
        name="New Name",
    )

    updated = service.update_account(
        user_id=test_user.id,
        account_id=account.id,
        data=data,
    )

    assert updated.name == "New Name"
    assert updated.currency == "NGN"
    assert updated.balance == Decimal("5000.000000000000")


def test_update_account_empty_patch_is_idempotent(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    An update containing no fields performs no changes.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        name="Original",
    )

    data = AccountUpdate()

    updated = service.update_account(
        user_id=test_user.id,
        account_id=account.id,
        data=data,
    )

    assert updated.id == account.id
    assert updated.name == "Original"


def test_update_account_cannot_modify_external_fields(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    AccountUpdate does not expose synchronization fields.

    The test verifies that normal user updates cannot establish
    an external connection.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountUpdate(
        name="Manual Account",
    )

    updated = service.update_account(
        user_id=test_user.id,
        account_id=account.id,
        data=data,
    )

    assert updated.is_connected is False
    assert updated.provider is None
    assert updated.external_account_id is None


def test_update_other_users_account_is_rejected(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    Users cannot update another user's account.
    """
    account = create_test_account(
        db,
        user_id=second_test_user.id,
    )

    data = AccountUpdate(
        name="Unauthorized Update",
    )

    with pytest.raises(NotFoundError):
        service.update_account(
            user_id=test_user.id,
            account_id=account.id,
            data=data,
        )


# =============================================================
# DEACTIVATION / ACTIVATION
# =============================================================

def test_deactivate_account(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Deactivation preserves the account but marks it inactive.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        is_active=True,
    )

    result = service.deactivate_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result.is_active is False


def test_deactivate_account_is_idempotent(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Deactivating an already inactive account is harmless.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        is_active=False,
    )

    result = service.deactivate_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result.is_active is False


def test_activate_account(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A previously inactive account can be reactivated.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        is_active=False,
    )

    result = service.activate_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result.is_active is True


def test_activate_account_is_idempotent(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Activating an already active account is harmless.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        is_active=True,
    )

    result = service.activate_account(
        user_id=test_user.id,
        account_id=account.id,
    )

    assert result.is_active is True


def test_status_operations_respect_ownership(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    Activation/deactivation cannot be used against another
    user's account.
    """
    account = create_test_account(
        db,
        user_id=second_test_user.id,
        is_active=True,
    )

    with pytest.raises(NotFoundError):
        service.deactivate_account(
            user_id=test_user.id,
            account_id=account.id,
        )

    with pytest.raises(NotFoundError):
        service.activate_account(
            user_id=test_user.id,
            account_id=account.id,
        )


# =============================================================
# SYNCHRONIZATION
# =============================================================

def test_sync_connects_account(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Trusted synchronization can connect a manual account.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    synced_at = datetime.now(timezone.utc)

    data = AccountSyncUpdate(
        balance=Decimal("150000.50"),
        is_connected=True,
        provider="Mono",
        external_account_id="mono-account-001",
        last_synced_at=synced_at,
    )

    updated = service.sync_account(
        account_id=account.id,
        data=data,
    )

    assert updated.balance == Decimal("150000.500000000000")
    assert updated.is_connected is True
    assert updated.provider == "Mono"
    assert updated.external_account_id == "mono-account-001"
    assert updated.last_synced_at == synced_at


def test_sync_can_update_balance_only(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    Partial synchronization updates are supported.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        balance=Decimal("1000.00"),
    )

    data = AccountSyncUpdate(
        balance=Decimal("5000.25"),
    )

    updated = service.sync_account(
        account_id=account.id,
        data=data,
    )

    assert updated.balance == Decimal("5000.250000000000")
    assert updated.is_connected is False


def test_sync_empty_update_is_idempotent(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    An empty synchronization update performs no changes.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        balance=Decimal("1000.00"),
    )

    data = AccountSyncUpdate()

    updated = service.sync_account(
        account_id=account.id,
        data=data,
    )

    assert updated.balance == Decimal("1000.000000000000")
    assert updated.is_connected is False


def test_sync_connected_account_requires_provider(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A connected account must have a provider.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountSyncUpdate(
        is_connected=True,
        external_account_id="external-001",
    )

    with pytest.raises(ValidationError):
        service.sync_account(
            account_id=account.id,
            data=data,
        )


def test_sync_connected_account_requires_external_id(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A connected account must have an external account ID.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountSyncUpdate(
        is_connected=True,
        provider="mono",
    )

    with pytest.raises(ValidationError):
        service.sync_account(
            account_id=account.id,
            data=data,
        )


def test_sync_disconnected_account_cannot_have_provider(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A disconnected account cannot retain a provider.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountSyncUpdate(
        provider="mono",
    )

    with pytest.raises(ValidationError):
        service.sync_account(
            account_id=account.id,
            data=data,
        )


def test_sync_disconnected_account_cannot_have_external_id(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A disconnected account cannot retain an external account ID.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
    )

    data = AccountSyncUpdate(
        external_account_id="external-001",
    )

    with pytest.raises(ValidationError):
        service.sync_account(
            account_id=account.id,
            data=data,
        )


def test_sync_disconnects_existing_connection(
    service: AccountService,
    test_user: User,
    db: Session,
) -> None:
    """
    A connected account can be disconnected by trusted
    synchronization infrastructure.

    Disconnecting also clears the provider identifiers.
    """
    account = create_test_account(
        db,
        user_id=test_user.id,
        is_connected=True,
        provider="mono",
        external_account_id="external-001",
    )

    data = AccountSyncUpdate(
        is_connected=False,
        provider=None,
        external_account_id=None,
    )

    updated = service.sync_account(
        account_id=account.id,
        data=data,
    )

    assert updated.is_connected is False
    assert updated.provider is None
    assert updated.external_account_id is None


def test_sync_missing_account(
    service: AccountService,
) -> None:
    """
    Synchronizing a missing account raises NotFoundError.
    """
    data = AccountSyncUpdate(
        balance=Decimal("100.00"),
    )

    with pytest.raises(NotFoundError):
        service.sync_account(
            account_id=999999999,
            data=data,
        )


def test_sync_duplicate_provider_account_is_conflict(
    service: AccountService,
    test_user: User,
    second_test_user: User,
    db: Session,
) -> None:
    """
    PostgreSQL's partial unique index prevents the same external
    provider account from being linked to multiple connected
    Account rows.
    """
    create_test_account(
        db,
        user_id=test_user.id,
        name="First Connected Account",
        is_connected=True,
        provider="mono",
        external_account_id="duplicate-external-id",
    )

    second_account = create_test_account(
        db,
        user_id=second_test_user.id,
        name="Second Connected Account",
    )

    data = AccountSyncUpdate(
        is_connected=True,
        provider="mono",
        external_account_id="duplicate-external-id",
    )

    with pytest.raises(ConflictError):
        service.sync_account(
            account_id=second_account.id,
            data=data,
        )


# =============================================================
# POSTGRESQL-SPECIFIC DATABASE BEHAVIOUR
# =============================================================

def test_postgresql_currency_constraint_rejects_invalid_value(
    db: Session,
    test_user: User,
) -> None:
    """
    Verify that PostgreSQL enforces the Account currency CHECK
    constraint independently of the service/schema layer.

    This intentionally bypasses AccountService and AccountCreate
    because the purpose is to test the actual PostgreSQL constraint.
    """
    account = Account(
        user_id=test_user.id,
        name="Invalid Currency Account",
        account_type=AccountType.BANK,
        institution_name=None,
        currency="usd-",
        balance=Decimal("100.00"),
        is_connected=False,
        provider=None,
        external_account_id=None,
        is_active=True,
        last_synced_at=None,
    )

    db.add(account)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_account_balance_precision_is_preserved(
    service: AccountService,
    test_user: User,
) -> None:
    """
    PostgreSQL Numeric(30,18) preserves supported financial
    decimal precision.
    """
    balance = Decimal("123456789012.123456789012345678")

    data = AccountCreate(
        name="Precision Account",
        account_type=AccountType.BANK,
        currency="NGN",
        balance=balance,
    )

    account = service.create_account(
        user_id=test_user.id,
        data=data,
    )

    assert account.balance == balance