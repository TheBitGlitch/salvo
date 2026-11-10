import pkgutil
import importlib
from typing import Annotated

from cyclopts import App
from cyclopts.parameter import Parameter

import tools

from .validators import runtime_validator
from .models import RuntimeArgs, RuntimeConfig

run_app = App(name="run", help="Launch a salvo against a target.")


@run_app.default
def run_command(
    args: Annotated[
        RuntimeArgs,
        Parameter(
            name="*",
            validator=runtime_validator,
        ),
    ],
) -> RuntimeConfig:
    """
    Resolves parsed CLI arguments into a runtime configuration.

    Args:
        args: Parsed and validated command-line arguments.

    Returns:
        The resolved runtime configuration.
    """
    return RuntimeConfig.from_args(args)


def manage_app() -> App:
    """
    Creates the application for auxiliary management commands.

    Returns:
        An application containing the automatically discovered management commands.
    """
    manage = App(name="manage", help="Perform auxiliary application operations.")

    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"tools.{module_name}")
        command = getattr(module, "__MANAGE_COMMAND__", None)

        if callable(command):
            manage.command(command, name=module_name.replace("_", "-"))

    return manage
