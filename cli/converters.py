from cyclopts.token import Token

from .regex_patterns import Patterns


def phone_converter(type_, value: tuple[Token]) -> str:
    """
    Normalizes a phone number by removing formatting and country prefixes.

    Args:
        value: Tokens containing the phone number to normalize.
    """
    phone_number: str = value[0].value.strip()

    phone_number = Patterns.PHONE_NORM.sub("", phone_number)

    if phone_number.startswith("98"):
        phone_number = phone_number[2:]

    if phone_number.startswith("0"):
        phone_number = phone_number[1:]

    return phone_number
