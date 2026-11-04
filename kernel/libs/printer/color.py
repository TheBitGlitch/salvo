from enum import StrEnum


class Color(StrEnum):
    """Vibrant ANSI 256-color palette for terminal output."""
    
    # Blues
    AZURE = "\033[38;5;39m"
    TURQUOISE = "\033[38;5;45m"
    AQUA = "\033[38;5;51m"
    SKY_BLUE = "\033[38;5;117m"
    DEEP_AQUA = "\033[38;5;44m"

    # Greens
    LIME = "\033[38;5;82m"
    MINT = "\033[38;5;46m"
    ACID = "\033[38;5;154m"

    # Yellows
    GOLD = "\033[38;5;220m"
    VERMILION = "\033[38;5;202m"

    # Reds
    CRIMSON = "\033[38;5;196m"
    CORAL = "\033[38;5;203m"
    HOT_PINK = "\033[38;5;201m"

    # Purples
    VIOLET = "\033[38;5;93m"
    LAVENDER = "\033[38;5;141m"

    # Neutral
    SLATE = "\033[38;5;244m"

    # Formatting
    RESET = "\033[0m"
