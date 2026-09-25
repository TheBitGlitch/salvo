from cyclopts.exceptions import ValidationError


class CliValidationError(ValidationError):
    """Base exception for CLI validation errors."""


class MalformedPhoneNumberError(CliValidationError):
    """Raised when a phone number has an invalid format."""

    def __init__(self, phone_number: str) -> None:
        super().__init__(f"Invalid phone number: `{phone_number}`.")


class MalformedProxyUrlError(CliValidationError):
    """Raised when a proxy URL has an invalid format."""

    def __init__(self, proxy_url: str) -> None:
        super().__init__(f"Invalid proxy URL: `{proxy_url}`.")


class UnsupportedProxyUrlError(CliValidationError):
    """Raised when a proxy URL uses an unsupported scheme."""

    def __init__(self, scheme: str) -> None:
        super().__init__(f"Unsupported proxy URL scheme: `{scheme}`.")
