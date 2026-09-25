from __future__ import annotations

from typing import TYPE_CHECKING

from .variants import ExecutionMode
from .regex_patterns import Patterns
from .exceptions import (
    CliValidationError,
    MalformedPhoneNumberError,
    MalformedProxyUrlError,
    UnsupportedProxyUrlError,
)

if TYPE_CHECKING:
    from .sub_apps import RuntimeArgs


def phone_validator(type_, phone_number: str) -> None:
    """
    Validates a normalized Iranian phone number.

    Args:
        phone_number: Normalized phone number to validate.

    Raises:
        MalformedPhoneNumberError: If the phone number has an invalid format.
    """
    if not Patterns.IR_PHONE.fullmatch(phone_number):
        raise MalformedPhoneNumberError(phone_number)


def proxy_validator(type_, proxy_url: str | None) -> None:
    """
    Validates a proxy URL and its supported scheme.

    Args:
        proxy_url: Proxy URL to validate.

    Raises:
        MalformedProxyUrlError: If the proxy URL has an invalid format.
        UnsupportedProxyUrlError: If the proxy URL uses an unsupported scheme.
    """
    if proxy_url is None:
        return

    proxy_url = proxy_url.strip()

    match = Patterns.PROXY.fullmatch(proxy_url)

    if not match:
        raise MalformedProxyUrlError(proxy_url)

    scheme = match.group("scheme")

    if scheme not in ("http", "https"):
        raise UnsupportedProxyUrlError(scheme)


def runtime_validator(type_, args: RuntimeArgs) -> None:
    """
    Validates the arguments used to configure application execution.

    Args:
        args: Execution arguments to validate.

    Raises:
        CliValidationError: If the arguments contain an invalid combination.
    """
    if args.mode is ExecutionMode.UNLIMITED:

        if args.limit is not None:
            raise CliValidationError(
                "The --limit option cannot be used with unlimited execution mode."
            )

        if args.fail_tolerance is not None:
            raise CliValidationError(
                "The --fail-tolerance option cannot be used with unlimited execution mode."
            )

        if args.fallback:
            raise CliValidationError(
                "The --fallback option cannot be used with unlimited execution mode."
            )

    if args.proxy is None and args.fallback:
        raise CliValidationError(
            "The --fallback option requires a proxy to be specified with --proxy."
        )
