from pathlib import Path
from typing import Annotated
from dataclasses import dataclass, asdict

from cyclopts import UNSET
from cyclopts.validators import Number
from cyclopts.parameter import Parameter

from default_path import DefaultPath

from .variants import ExecutionMode
from .converters import phone_converter
from .validators import phone_validator, proxy_validator


@dataclass(frozen=True, slots=True)
class RuntimeArgs:
    """
    Represents the raw arguments provided through the command-line interface.

    Contains parsed and validated CLI inputs, including values that may
    require resolution before being used by the application.
    """

    target: Annotated[
        str,
        Parameter(
            alias=["-t", "--target"],
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

    fail_tolerance: Annotated[
        int | UNSET,
        Parameter(
            name="--fail-tolerance",
            help="Maximum number of consecutive failures tolerated.",
            show_default="6 (LIMITED mode)",
            validator=Number(gte=6),
        ),
    ] = UNSET

    concurrency: Annotated[
        int,
        Parameter(
            name=["-c", "--concurrency"],
            help="Maximum number of concurrent workers.",
            validator=Number(gte=1),
        ),
    ] = 6

    timeout: Annotated[
        float,
        Parameter(
            name="--timeout",
            help="Request timeout in seconds.",
            validator=Number(gt=0),
        ),
    ] = 5.0

    proxy: Annotated[
        str | None,
        Parameter(
            name=["-p", "--proxy"],
            help="Proxy server to use for requests (HTTP/HTTPS).",
            validator=proxy_validator,
        ),
    ] = None

    ssl: Annotated[
        bool,
        Parameter(
            name="--ssl",
            negative="--no-ssl",
            help="Enable SSL certificate verification.",
        ),
    ] = True

    fallback: Annotated[
        bool,
        Parameter(
            name="--fallback",
            negative="--no-fallback",
            help="Switch from proxy to direct connection after --fail-tolerance consecutive failures.",
        ),
    ] = False

    endpoints: Annotated[
        Path,
        Parameter(
            name=["-e", "--endpoints"],
            help="Path to the endpoint configuration.",
        ),
    ] = DefaultPath.ENDPOINTS_JSON

    color: Annotated[
        bool,
        Parameter(
            name="--color",
            negative="--no-color",
            help="Enable colored console output.",
        ),
    ] = True

    verbose: Annotated[
        bool,
        Parameter(
            name="--verbose",
            negative="--no-verbose",
            help="Enable DEBUG logging for additional diagnostic information.",
        ),
    ] = False


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """
    Represents the resolved runtime configuration of the application.

    Contains normalized and finalized settings required to initialize
    and execute the application.
    """

    target: str
    mode: ExecutionMode
    limit: int | None
    fail_tolerance: int | None
    concurrency: int
    timeout: float
    proxy: str | None
    ssl: bool
    fallback: bool
    endpoints: Path
    color: bool
    verbose: bool

    @classmethod
    def from_args(cls, args: RuntimeArgs) -> "RuntimeConfig":
        """
        Creates a runtime configuration from parsed command-line arguments.

        Resolves mode-dependent defaults and converts unset optional values
        into their effective runtime values.

        Args:
            args: Parsed command-line arguments.

        Returns:
            A fully resolved runtime configuration.
        """
        fail_tolerance = (
            (6 if args.fail_tolerance is UNSET else args.fail_tolerance)
            if args.mode is ExecutionMode.LIMITED
            else None
        )

        return cls(
            target=args.target,
            mode=args.mode,
            limit=args.limit,
            fail_tolerance=fail_tolerance,
            concurrency=args.concurrency,
            timeout=args.timeout,
            proxy=args.proxy,
            ssl=args.ssl,
            fallback=args.fallback,
            endpoints=args.endpoints,
            color=args.color,
            verbose=args.verbose,
        )

    @property
    def bounded(self) -> bool:
        return self.mode is ExecutionMode.LIMITED

    @property
    def asdict(self) -> dict:
        return asdict(self)
