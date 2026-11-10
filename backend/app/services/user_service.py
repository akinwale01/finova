from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    FinovaError,
    NotFoundError,
    ValidationError,
)
from backend.app.models.user import User
from backend.app.schemas.user import (
    PasswordChange,
    PasswordResetConfirm,
    UserCreate,
    UserUpdate,
)
from backend.app.services.base_service import BaseService


class UserService(BaseService[User]):
    """
    Business/service layer for Finova users.

    Responsibilities:
        - User retrieval
        - User creation
        - Email uniqueness
        - Password hashing and verification
        - Profile updates
        - Password changes
        - Account activation/deactivation
        - Login metadata
        - Email verification state
        - Password-reset token lifecycle

    Deliberately does NOT:
        - Generate JWT access tokens
        - Send emails
        - Render API responses
        - Perform HTTP-specific logic
        - Hard-delete users
        - Decide authorization policy outside the user domain

    Password hashing and verification implementations are
    injected into the service so the service remains independent
    of a particular password-hashing library.
    """

    model = User

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(
        self,
        db: Session,
        password_hasher: Callable[[str], str],
        password_verifier: Callable[[str, str], bool],
    ) -> None:
        """
        Initialize the UserService.

        Args:
            db:
                Active SQLAlchemy session owned by the application
                or request layer.

            password_hasher:
                Callable that accepts a plaintext password and
                returns its secure password hash.

            password_verifier:
                Callable that accepts a plaintext password and
                stored password hash and returns whether they match.

        The service does not create or close the database session.
        """

        super().__init__(db)

        self._password_hasher = password_hasher
        self._password_verifier = password_verifier

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def get_user(self, user_id: int) -> User | None:
        """
        Retrieve a user by primary key.

        Returns:
            User instance when found.
            None when the user does not exist.
        """

        return self.get_by_id(user_id)

    def require_user(self, user_id: int) -> User:
        """
        Retrieve a user by primary key.

        Raises:
            NotFoundError:
                If the user does not exist.
        """

        return self.require_by_id(
            user_id,
            "User",
        )

    def get_by_email(self, email: str) -> User | None:
        """
        Retrieve a user by normalized email address.

        User.email is normalized by the User model on writes,
        and this service normalizes lookup values as well.
        """

        normalized_email = self._normalize_email(email)

        return (
            self.db.query(User)
            .filter(User.email == normalized_email)
            .first()
        )

    def require_by_email(self, email: str) -> User:
        """
        Retrieve a user by email.

        Raises:
            NotFoundError:
                If no user exists for the supplied email.
        """

        normalized_email = self._normalize_email(email)

        user = self.get_by_email(normalized_email)

        if user is None:
            raise NotFoundError(
                f"User with email '{normalized_email}' was not found."
            )

        return user

    # =========================================================
    # CREATION
    # =========================================================

    def create_user(self, data: UserCreate) -> User:
        """
        Create and persist a new Finova user.

        The plaintext password is never stored. It is passed
        immediately to the injected password hasher.

        Raises:
            ConflictError:
                If the email address already belongs to a user.

            FinovaError:
                If password hashing or database persistence fails.
        """

        normalized_email = self._normalize_email(
            str(data.email)
        )

        # Fast application-level conflict check.
        #
        # The database unique index remains the authoritative
        # protection against concurrent duplicate inserts.
        if self.get_by_email(normalized_email) is not None:
            raise ConflictError(
                "A user with this email address already exists."
            )

        password_hash = self._hash_password(
            data.password
        )

        user = User(
            email=normalized_email,
            password_hash=password_hash,
            is_active=True,
        )

        self.add(user)

        # Flush first so the database unique constraint is
        # evaluated here. This allows us to distinguish a
        # duplicate-email IntegrityError from other DB errors.
        try:
            self.flush()
        except IntegrityError as exc:
            self.rollback()

            raise ConflictError(
                "A user with this email address already exists."
            ) from exc
        except SQLAlchemyError as exc:
            self.rollback()

            raise FinovaError(
                "Unable to create user."
            ) from exc

        # BaseService.commit() owns the normal commit behavior
        # and converts unexpected SQLAlchemy errors into
        # FinovaError.
        self.commit(user)

        return user

    # =========================================================
    # PROFILE UPDATE
    # =========================================================

    def update_user(
        self,
        user_id: int,
        data: UserUpdate,
    ) -> User:
        """
        Update user-controlled profile fields.

        Currently UserUpdate permits changing only the email
        address.

        Raises:
            NotFoundError:
                If the user does not exist.

            ConflictError:
                If another user already owns the requested email.

            FinovaError:
                If persistence fails.
        """

        user = self.require_user(user_id)

        if data.email is None:
            return user

        normalized_email = self._normalize_email(
            str(data.email)
        )

        # No database write is necessary if the email has not
        # actually changed.
        if normalized_email == user.email:
            return user

        existing_user = self.get_by_email(
            normalized_email
        )

        if (
            existing_user is not None
            and existing_user.id != user.id
        ):
            raise ConflictError(
                "A user with this email address already exists."
            )

        user.email = normalized_email

        try:
            self.flush()
        except IntegrityError as exc:
            self.rollback()

            raise ConflictError(
                "A user with this email address already exists."
            ) from exc
        except SQLAlchemyError as exc:
            self.rollback()

            raise FinovaError(
                "Unable to update user."
            ) from exc

        self.commit(user)

        return user

    # =========================================================
    # PASSWORD CHANGE
    # =========================================================

    def change_password(
        self,
        user_id: int,
        data: PasswordChange,
    ) -> User:
        """
        Change the password of an existing user.

        The current password must be verified before the new
        password is accepted.

        Any outstanding password-reset token is invalidated.

        Raises:
            NotFoundError:
                If the user does not exist.

            AuthorizationError:
                If the account is inactive or the current password
                is incorrect.

            BusinessRuleError:
                If the new password is identical to the current
                password.

            FinovaError:
                If hashing or persistence fails.
        """

        user = self.require_user(user_id)

        if not user.is_active:
            raise AuthorizationError(
                "Inactive users cannot change their password."
            )

        if not self._verify_password(
            data.current_password,
            user.password_hash,
        ):
            raise AuthorizationError(
                "The current password is incorrect."
            )

        if self._verify_password(
            data.new_password,
            user.password_hash,
        ):
            raise BusinessRuleError(
                "The new password must be different from the current password."
            )

        user.password_hash = self._hash_password(
            data.new_password
        )

        # Explicit password changes invalidate any outstanding
        # password-reset credentials.
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None

        self.commit(user)

        return user

    # =========================================================
    # ACCOUNT STATUS
    # =========================================================

    def deactivate_user(self, user_id: int) -> User:
        """
        Deactivate a user without deleting their financial data.

        Users are intentionally not hard-deleted.

        Outstanding password-reset credentials are invalidated.

        Raises:
            NotFoundError:
                If the user does not exist.

            FinovaError:
                If persistence fails.
        """

        user = self.require_user(user_id)

        if not user.is_active:
            return user

        user.is_active = False

        # Prevent an inactive account from retaining a usable
        # password-reset credential.
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None

        self.commit(user)

        return user

    def activate_user(self, user_id: int) -> User:
        """
        Reactivate a previously deactivated user.

        Raises:
            NotFoundError:
                If the user does not exist.

            FinovaError:
                If persistence fails.
        """

        user = self.require_user(user_id)

        if user.is_active:
            return user

        user.is_active = True

        self.commit(user)

        return user

    # =========================================================
    # AUTHENTICATION
    # =========================================================

    def authenticate(
        self,
        email: str,
        password: str,
    ) -> User:
        """
        Authenticate a user using email and password.

        Successful authentication updates last_login_at.

        Raises:
            AuthorizationError:
                If credentials are invalid or the account is
                inactive.

            FinovaError:
                If successful authentication cannot persist the
                login metadata.
        """

        user = self.get_by_email(email)

        # Do not reveal whether a supplied email address belongs
        # to a Finova account.
        if user is None:
            raise AuthorizationError(
                "Invalid email or password."
            )

        if not user.is_active:
            raise AuthorizationError(
                "Invalid email or password."
            )

        if not self._verify_password(
            password,
            user.password_hash,
        ):
            raise AuthorizationError(
                "Invalid email or password."
            )

        user.last_login_at = datetime.now(
            timezone.utc
        )

        try:
            self.commit(user)
        except FinovaError as exc:
            # Authentication itself succeeded, but the login
            # metadata could not be persisted.
            raise FinovaError(
                "Authentication succeeded, but login metadata "
                "could not be updated."
            ) from exc

        return user

    # =========================================================
    # EMAIL VERIFICATION
    # =========================================================

    def mark_email_verified(
        self,
        user_id: int,
    ) -> User:
        """
        Mark a user's email address as verified.

        Verification is idempotent: verifying an already
        verified user does not modify the existing timestamp.

        Raises:
            NotFoundError:
                If the user does not exist.

            FinovaError:
                If persistence fails.
        """

        user = self.require_user(user_id)

        if user.email_verified_at is not None:
            return user

        user.email_verified_at = datetime.now(
            timezone.utc
        )

        self.commit(user)

        return user

    # =========================================================
    # PASSWORD RESET — TOKEN CREATION
    # =========================================================

    def create_password_reset_token(
        self,
        email: str,
        expires_at: datetime,
    ) -> str | None:
        """
        Create a password-reset token for an active user.

        Only the SHA-256 hash of the token is persisted.

        The raw token is returned exactly once to the caller,
        which is responsible for delivering it through the
        appropriate password-reset channel.

        Returns:
            Raw reset token for an existing active user.
            None when the email does not correspond to an active
            user.

        Raises:
            ValidationError:
                If expires_at is naive or not in the future.

            FinovaError:
                If persistence fails.
        """

        if expires_at.tzinfo is None:
            raise ValidationError(
                "Password reset expiration must include timezone information."
            )

        now = datetime.now(timezone.utc)

        if expires_at <= now:
            raise ValidationError(
                "Password reset expiration must be in the future."
            )

        user = self.get_by_email(email)

        # Returning None for both unknown and inactive accounts
        # prevents the reset-request operation from becoming an
        # account-enumeration mechanism.
        if user is None or not user.is_active:
            return None

        raw_token = secrets.token_urlsafe(32)

        user.password_reset_token_hash = (
            self._hash_reset_token(raw_token)
        )

        user.password_reset_expires_at = expires_at

        self.commit(user)

        return raw_token

    # =========================================================
    # PASSWORD RESET — CONFIRMATION
    # =========================================================

    def reset_password(
        self,
        data: PasswordResetConfirm,
    ) -> User:
        """
        Complete a password reset using the supplied raw token.

        Reset tokens are:
            - stored only as SHA-256 hashes
            - time-limited
            - single-use
            - invalidated after successful reset

        Raises:
            AuthorizationError:
                If the token is invalid, expired, or belongs to
                an inactive account.

            BusinessRuleError:
                If the new password is identical to the current
                password.

            FinovaError:
                If persistence fails.
        """

        token_hash = self._hash_reset_token(
            data.token
        )

        user = (
            self.db.query(User)
            .filter(
                User.password_reset_token_hash
                == token_hash
            )
            .first()
        )

        if user is None:
            raise AuthorizationError(
                "Invalid or expired password reset token."
            )

        if not user.is_active:
            raise AuthorizationError(
                "Invalid or expired password reset token."
            )

        expires_at = user.password_reset_expires_at

        if expires_at is None:
            raise AuthorizationError(
                "Invalid or expired password reset token."
            )

        now = datetime.now(timezone.utc)

        if expires_at <= now:
            # Remove the expired credential from the database.
            user.password_reset_token_hash = None
            user.password_reset_expires_at = None

            try:
                self.commit(user)
            except FinovaError as exc:
                raise FinovaError(
                    "Unable to invalidate expired password reset token."
                ) from exc

            raise AuthorizationError(
                "Invalid or expired password reset token."
            )

        if self._verify_password(
            data.new_password,
            user.password_hash,
        ):
            raise BusinessRuleError(
                "The new password must be different from the current password."
            )

        user.password_hash = self._hash_password(
            data.new_password
        )

        # Reset credentials are single-use.
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None

        self.commit(user)

        return user

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    @staticmethod
    def _normalize_email(email: str) -> str:
        """
        Normalize an email address for service-level equality.

        The User SQLAlchemy model performs the same normalization
        when the value is assigned to the model.
        """

        if not isinstance(email, str):
            raise ValidationError(
                "Email must be a string."
            )

        normalized = email.strip().lower()

        if not normalized:
            raise ValidationError(
                "Email cannot be empty."
            )

        return normalized

    def _hash_password(self, password: str) -> str:
        """
        Hash a plaintext password using the injected hasher.

        Unexpected hashing-library failures are converted into
        FinovaError so implementation details do not leak from
        the service layer.
        """

        try:
            hashed = self._password_hasher(password)
        except Exception as exc:
            raise FinovaError(
                "Unable to securely hash password."
            ) from exc

        if not isinstance(hashed, str) or not hashed:
            raise FinovaError(
                "Password hashing did not return a valid hash."
            )

        return hashed

    def _verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        """
        Verify a plaintext password against its stored hash.

        Unexpected hashing-library failures are converted into
        FinovaError.
        """

        try:
            return bool(
                self._password_verifier(
                    password,
                    password_hash,
                )
            )
        except Exception as exc:
            raise FinovaError(
                "Unable to verify password."
            ) from exc

    @staticmethod
    def _hash_reset_token(token: object) -> str:
        """
        SHA-256 hash a password-reset token before persistence.

        The raw reset token must never be stored in the database.
        """

        if not isinstance(token, str):
            raise ValidationError(
                "Password reset token must be a string."
            )

        if not token:
            raise ValidationError(
                "Password reset token cannot be empty."
            )

        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()