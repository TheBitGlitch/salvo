import sys
from pathlib import Path
from collections.abc import Sequence


def get_invocation(black_list: Sequence[str] = []) -> str | None:
    """
    Returns the current command-line invocation.

    The executable path is replaced with its filename stem,
    Commands listed in `black_list` are excluded from the returned invocation.
    """
    argv = sys.argv.copy()

    if argv:
        argv[0] = Path(argv[0]).stem

    invocation = " ".join(argv)

    if any(command in invocation for command in black_list):
        return None

    return invocation
