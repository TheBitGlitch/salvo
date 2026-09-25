from enum import StrEnum


class Color(StrEnum):
    """ANSI escape codes for terminal colors using standard and 256-color palettes."""

    BLACK = "\033[38;5;0m"
    BLUE = "\033[94m"
    BROWN = "\033[38;5;130m"
    CYAN = "\033[96m"
    GRAY = "\033[38;5;245m"
    GREEN = "\033[92m"
    MAGENTA = "\033[38;5;201m"
    ORANGE = "\033[38;5;208m"
    PINK = "\033[38;5;205m"
    PURPLE = "\033[95m"
    RED = "\033[91m"
    SWAMP = "\033[38;5;64m"
    WHITE = "\033[38;5;255m"
    YELLOW = "\033[93m"

    LIGHT_BLUE = "\033[38;5;117m"
    LIGHT_CYAN = "\033[38;5;159m"
    LIGHT_GRAY = "\033[38;5;250m"
    LIGHT_GREEN = "\033[38;5;120m"
    LIGHT_ORANGE = "\033[38;5;215m"
    LIGHT_PURPLE = "\033[38;5;219m"
    LIGHT_RED = "\033[38;5;203m"
    LIGHT_YELLOW = "\033[38;5;229m"

    RESET = "\033[0m"
