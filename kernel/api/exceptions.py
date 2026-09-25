from pathlib import Path


class ApiError(Exception):
    """Base exception for API errors."""


class LoadApiEndpointsError(ApiError):
    """Raised when the endpoints JSON file cannot be loaded."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Failed to load API endpoints from `{path}`.")


class ApiEndpointsNotFoundError(ApiError):
    """Raised when the API endpoints file does not exist."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"API endpoints file was not found at `{path}`.\n\n"
            "To download the required endpoints, run:\n"
            "    salvo manage sync-endpoints\n"
        )


class NoValidApiEndpointFoundError(ApiError):
    """Raised when no valid API endpoint configurations are found."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"No valid API endpoints found in `{path}`.")
