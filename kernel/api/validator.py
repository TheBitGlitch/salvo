import re
from typing import Any


class ApiValidator:
    """
    Validates API configuration dictionaries before they are converted
    into runtime API objects (ApiSlot).

    Valid endpoint configuration template:
        [
            {
                "source": "example.com",
                "url": "https://example.com/send-sms/",
                "method": "POST",
                "capacity": 50,
                "ticket": 100,
                "json": {
                    "phone": "+98{phone}"
                }
            },
            {
                "source": "sample.org",
                "url": "https://sample.org/send-sms/phone=?{phone}",
                "method": "GET",
                "capacity": 20,
                "ticket": 56
            }
        ]

    Required fields:
        source: API source identifier.
        url: Target endpoint URL.
        method: HTTP method (`GET` or `POST`).
        capacity: Execution capacity per phone number per cycle.
        ticket: Weight used by the API pool to prioritize API selection.

    Optional fields:
        json: JSON request payload.
        data: Form-data request payload.

    Notes:
        `json` and `data` are mutually exclusive.
    """

    _URL_REGEX_PATTERN: re.Pattern = re.compile(
        r"^(https?|ftp)://"
        r"(?:(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}|localhost)"
        r"(?::\d{1,5})?"
        r"(?:/\S*)?$"
    )

    _REQUIRED_FIELDS = ("source", "url", "method", "capacity", "ticket")

    @classmethod
    def validate(cls, endpoint: dict[str, Any]) -> bool:
        """
        Validates a complete API configuration.

        Returns:
            `True` if the configuration is valid, `False` otherwise.
        """
        if any(k not in endpoint for k in cls._REQUIRED_FIELDS):
            return False

        json_body = endpoint.get("json")
        data_body = endpoint.get("data")

        if json_body is not None and data_body is not None:
            return False

        return (
            cls._validate_source(endpoint["source"])
            and cls._validate_url(endpoint["url"])
            and cls._validate_method(endpoint["method"])
            and cls._validate_positive_int(endpoint["capacity"])
            and cls._validate_positive_int(endpoint["ticket"])
            and cls._validate_payload(json_body)
            and cls._validate_payload(data_body)
        )

    @classmethod
    def _validate_url(cls, url: Any) -> bool:
        if not isinstance(url, str):
            return False

        return bool(cls._URL_REGEX_PATTERN.fullmatch(url))

    @staticmethod
    def _validate_source(source: Any) -> bool:
        """
        Validates the API source identifier.

        The source must be a non-empty string and must not start with `#`.
        """
        if not isinstance(source, str):
            return False

        source = source.strip()

        return bool(source) and not source.startswith("#")

    @staticmethod
    def _validate_method(method: Any) -> bool:
        if not isinstance(method, str):
            return False

        return method in ("POST", "GET")

    @staticmethod
    def _validate_positive_int(value: Any) -> bool:
        """Validates that the value is a strictly positive integer."""
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _validate_payload(value: Any) -> bool:
        """Validates that the payload is either `None` or a dictionary."""
        return value is None or isinstance(value, dict)
