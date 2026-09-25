import pkgutil
import importlib
from pathlib import Path
from typing import Annotated
from dataclasses import dataclass, asdict

from cyclopts import App
from cyclopts.validators import Number
from cyclopts.parameter import Parameter

import tools
from default_path import DefaultPath

from .variants import ExecutionMode
from .converters import phone_converter
from .validators import phone_validator, proxy_validator, runtime_validator

run_app = App(name="run", help="Launch a salvo against a target.")


def manage_app() -> App:
    """
    Creates the application for auxiliary management commands.

    Returns:
        An application containing the automatically discovered management commands.
    """
    manage = App(name="manage", help="Perform auxiliary application operations.")

    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"tools.{module_name}")
        command = getattr(module, "COMMAND", None)

        if callable(command):
            manage.command(command, name=module_name.replace("_", "-"))

    return manage


@dataclass(slots=True)
class RuntimeArgs:
    """Defines the arguments used to configure application execution."""

    target: Annotated[
        str,
        Parameter(
            name=["-t", "--target"],
            help="Target phone number.",
            converter=phone_converter,
            validator=phone_validator,
        ),
    ]

    mode: Annotated[
        ExecutionMode,
        Parameter(
            name=["-m", "--mode"],
            help="Execution mode.",
        ),
    ] = ExecutionMode.LIMITED

    limit: Annotated[
        int | None,
        Parameter(
            name=["-l", "--limit"],
            help="Stop execution after the specified number of successful attacks.",
            validator=Number(gte=1),
        ),
    ] = None

    concurrency: Annotated[
        int,
        Parameter(
            name=["-c", "--concurrency"],
            help="Maximum number of concurrent workers.",
            validator=Number(gte=1),
        ),
    ] = 6

    proxy: Annotated[
        str | None,
        Parameter(
            name=["-p", "--proxy"],
            help="Proxy server to use for requests (HTTP/HTTPS).",
            validator=proxy_validator,
        ),
    ] = None

    endpoints: Annotated[
        Path,
        Parameter(
            name="--endpoints",
            help="Path to the endpoint configuration.",
        ),
    ] = DefaultPath.ENDPOINTS_JSON

    fail_tolerance: Annotated[
        int | None,
        Parameter(
            name="--fail-tolerance",
            help="Maximum number of consecutive failures tolerated.",
        ),
    ] = None

    timeout: Annotated[
        int,
        Parameter(
            name="--timeout",
            help="Request timeout in seconds.",
            validator=Number(gte=1),
        ),
    ] = 5

    fallback: Annotated[
        bool,
        Parameter(
            name="--fallback",
            help="Enable fallback to alternative endpoints.",
        ),
    ] = False

    ssl: Annotated[
        bool,
        Parameter(
            name="--ssl",
            help="Enable SSL certificate verification.",
        ),
    ] = False

    def __post_init__(self) -> None:
        if self.fail_tolerance is None and self.mode is ExecutionMode.LIMITED:
            self.fail_tolerance = 6

    @property
    def bounded(self) -> bool:
        return self.mode is ExecutionMode.LIMITED

    @property
    def asdict(self) -> dict:
        """Returns the execution arguments as a dictionary."""
        return asdict(self)


@run_app.default
def run_command(
    args: Annotated[
        RuntimeArgs,
        Parameter(
            name="*",
            validator=runtime_validator,
        ),
    ],
) -> RuntimeArgs:
    """
    Returns the parsed execution arguments.

    Args:
        args: Execution arguments provided through the CLI.

    Returns:
        The parsed execution arguments.
    """

    return args
