"""
Common application exceptions used by Finova services.
"""

from app.exceptions.base import FinovaError


class NotFoundError(FinovaError):
    """Raised when a requested resource does not exist."""

    default_message = "The requested resource was not found."


class ConflictError(FinovaError):
    """Raised when an operation conflicts with existing data."""

    default_message = "The requested operation conflicts with existing data."


class ValidationError(FinovaError):
    """Raised when business-level validation fails."""

    default_message = "The supplied data is invalid."


class AuthorizationError(FinovaError):
    """Raised when the current user cannot access a resource."""

    default_message = "You are not authorized to access this resource."


class BusinessRuleError(FinovaError):
    """Raised when a Finova business rule prevents an operation."""

    default_message = "The requested operation violates a business rule."
