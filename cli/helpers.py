import sys
from pathlib import Path
from collections.abc import Callable, Sequence


def get_invocation(blacklist: Sequence[str] | None = None) -> str | None:
    """
    Returns the current command-line invocation.

    The executable path is replaced with its filename stem.
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


def register_manage_command(function: Callable[..., object]) -> Callable[..., object]:
    """
    Registers a function as a management command for automatic discovery.

    Registered commands are discovered by the manage application in the
    `cli/sub_apps.py` module.

    Args:
        function: The function to register as a management command.

    Returns:
        The original function.
    """
    module = sys.modules[function.__module__]
    setattr(module, "__MANAGE_COMMAND__", function)

    return function
