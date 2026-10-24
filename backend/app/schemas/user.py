import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Centralize the rule so UserCreate and PasswordChange can't
# drift apart over time.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def _validate_password_strength(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit.")
    return value


class UserBase(BaseModel):
    """
    Shared fields for User API schemas.
    """

    email: EmailStr


class UserCreate(UserBase):
    """
    Data required when creating a new Finova user.
    """

    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="Plaintext password. Hashed before storage; never persisted as-is.",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserLogin(BaseModel):
    """
    Data required when logging into Finova.
    """

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """
    Profile fields a user may change about themselves.

    Deliberately excludes password (use PasswordChange, which
    requires the current password) and excludes is_active,
    email_verified_at, last_login_at (system/admin-controlled).
    """

    email: EmailStr | None = None


class PasswordChange(BaseModel):
    """
    Schema for an authenticated user changing their own
    password.

    Requiring current_password prevents a hijacked/unattended
    session (or a stolen bearer token) from being used to lock
    the real owner out by silently resetting the password.
    """

    current_password: str
    new_password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class PasswordResetRequest(BaseModel):
    """
    Step 1 of the "forgot password" flow: user submits their
    email to receive a reset link/code.
    """

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """
    Step 2 of the "forgot password" flow: user submits the
    token they received plus a new password.
    """

    token: str
    new_password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserResponse(UserBase):
    """
    Safe User representation returned by the API.

    Never expose:
        - password
        - password_hash
        - password_reset_token_hash
    """

    id: int
    is_active: bool
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )