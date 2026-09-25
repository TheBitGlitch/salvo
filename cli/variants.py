from enum import StrEnum


class ExecutionMode(StrEnum):
    """Defines the available modes for application execution."""

    LIMITED = "limited"
    UNLIMITED = "unlimited"
