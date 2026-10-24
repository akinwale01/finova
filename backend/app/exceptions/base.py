"""
Base exception infrastructure for Finova.

Application-specific exceptions inherit from FinovaError so the API
layer can reliably distinguish expected application failures from
unexpected Python/database errors.
"""


class FinovaError(Exception):
    """
    Base class for all expected Finova application exceptions.

    Services should raise FinovaError subclasses for predictable
    business/application failures. Unexpected programming errors
    should not be converted into FinovaError automatically.
    """

    default_message = "An application error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)
