import sys
from pathlib import Path
from collections.abc import Sequence


def get_invocation(blacklist: Sequence[str] | None = None) -> str | None:
    """
    Returns the current command-line invocation.

    The executable path is replaced with its filename stem,
    Commands listed in `blacklist` are excluded from the returned invocation.
    """
    blacklist = blacklist or ()
    argv = sys.argv.copy()

    if argv:
        argv[0] = Path(argv[0]).stem

    invocation = " ".join(argv)

    if any(command in invocation for command in blacklist):
        return None

    return invocation
