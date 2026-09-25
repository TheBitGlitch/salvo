import re


class Patterns:
    """Defines the compiled regular expression patterns used by the CLI."""

    PROXY: re.Pattern = re.compile(
        r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://"
        r"(?:[^:@\s]+:[^:@\s]*@)?"
        r"(?:"
        r"\[[0-9a-fA-F:]+\]|"
        r"(?:\d{1,3}\.){3}\d{1,3}|"
        r"[a-zA-Z0-9.-]+"
        r")"
        r"(?::\d{1,5})?"
        r"(?:/.*)?$"
    )

    IR_PHONE: re.Pattern = re.compile(r"^(?:0?9\d{9}|98(?:0)?9\d{9})$")

    PHONE_NORM: re.Pattern = re.compile(r"[^0-9]")
