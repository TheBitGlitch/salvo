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

    NOTICE = ("NOTICE", Color.TURQUOISE)
    DEBUG = ("DEBUG", Color.SLATE)
    WARNING = ("WARNING", Color.GOLD)
    ERROR = ("ERROR", Color.CRIMSON)
    CRITICAL = ("CRITICAL", Color.HOT_PINK)


class EventTag(Tag):
    """Tags used to indicate application lifecycle and state changes."""

    PURGED = ("PURGED", Color.VERMILION)
    JAILED = ("JAILED", Color.VIOLET)
    FREED = ("FREED", Color.SKY_BLUE)

    FALLBACK = ("FALLBACK", Color.AZURE)


class SystemTag(Tag):
    """Tags used for system-level messages."""

    MANIFEST = ("MANIFEST", Color.AQUA)
    SUMMARY = ("SUMMARY", Color.DEEP_AQUA)
    

class ResponseTag(Tag):
    """Tags used to indicate possible outcomes from an API request."""

    SUCCESS = ("SUCCESS", Color.MINT)
    FAILURE = ("FAILURE", Color.CORAL)
    ZOMBIE = ("ZOMBIE", Color.SWAMP)
