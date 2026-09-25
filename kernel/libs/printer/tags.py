from enum import Enum

from .color import Color


class Tag(Enum):
    """Defines a labeled terminal tag with an associated color."""

    def __init__(self, label: str, color: Color) -> None:
        self._label = label
        self._color = color

    def __str__(self) -> str:
        return self._label

    @property
    def label(self) -> str:
        return self._label

    @property
    def color(self) -> Color:
        return self._color


class SeverityTag(Tag):
    """Tags used to indicate message severity levels."""

    ERROR = ("ERROR", Color.RED)
    NOTICE = ("NOTICE", Color.CYAN)
    WARNING = ("WARNING", Color.YELLOW)
    CRITICAL = ("CRITICAL", Color.MAGENTA)


class EventTag(Tag):
    """Tags used to indicate application lifecycle and state changes."""

    PURGED = ("PURGED", Color.PINK)
    JAILED = ("JAILED", Color.ORANGE)
    FREED = ("FREED", Color.LIGHT_BLUE)

    FALLBACK = ("FALLBACK", Color.BLUE)


class SystemTag(Tag):
    """Tags used for system-level messages."""

    SUMMARY = ("SUMMARY", Color.CYAN)


class ResponseTag(Tag):
    """Tags used to indicate possible outcomes from an API request."""

    SUCCESS = ("SUCCESS", Color.GREEN)
    FAILURE = ("FAILURE", Color.RED)
    ZOMBIE = ("ZOMBIE", Color.SWAMP)
