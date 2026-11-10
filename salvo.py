# Copyright (c) 2026 TheBitGlitch
# SPDX-License-Identifier: MIT

import sys
import socket

from cli import app as cli_app
from cli.models import RuntimeConfig
from cli.helpers import get_invocation

from kernel.core import Engine
from kernel.api import ApiFactory
from kernel.api.exceptions import ApiError
from kernel.libs.printer import Console

from tools.history import History


def check_network_access(timeout: float = 10) -> bool:
    """Checks whether a network connection can be established."""
    try:
        with socket.create_connection(address=("google.com", 443), timeout=timeout):
            return True

    except OSError:
        return False


def terminate(status: int = 0) -> None:
    """Exits the program with the specified exit code."""
    sys.exit(status)


def main() -> None:
    HISTORY_BLACKLIST = (
        "clear-data",
        "history",
    )

    if invocation := get_invocation(HISTORY_BLACKLIST):
        History.add(invocation)

    # Management commands complete their work without producing runtime configuration.
    runtime_config: RuntimeConfig | None = cli_app()

    if runtime_config is None:
        terminate()  # No runtime execution is needed

    console = Console(
        verbose=runtime_config.verbose,
        colored=runtime_config.color,
    )

    console.clear_screen()
    console.manifest(runtime_config.asdict)

    if runtime_config.proxy is None:
        console.warning(
            "No proxy configured. Requests will use a direct connection."
        )

    if not runtime_config.ssl:
        console.warning(
            "SSL verification is disabled. Server certifications will not be verified."
        )

    if runtime_config.fallback:
        console.warning(
            "Proxy fallback is enabled. Requests will fall back to a direct connection after repeated proxy failures."
        )

    if not check_network_access():
        console.error(
            "No network connection detected. Please check your internet connection and try again."
        )
        terminate(1)

    try:
        api_factory = ApiFactory(
            endpoints_path=runtime_config.endpoints,
            context={"phone": runtime_config.target},
        )
        api_factory.build()

        console.notice(f"Loaded {api_factory.slot_count} valid API endpoints.")

        if api_factory.dropped_count > 0:
            console.debug(
                f"{api_factory.dropped_count} API endpoints failed validation "
                "and were excluded from this execution."
            )

    except ApiError as exc:
        console.error(str(exc))
        terminate(1)
    
    proceed = console.input("Review complete. Proceed? (y/n): ").lower()

    if proceed not in ("y", "yes"):
        console.notice("Execution aborted by operator.")
        terminate()

    console.notice("Press Ctrl+C at any time to abort execution.")

    try:
        engine = Engine(
            api_slots=api_factory.api_slots,
            runtime_config=runtime_config,
            console=console,
        )
        engine.launch()

    except Exception as exc:
        console.error(f"Execution failed: {str(exc)}")

        if runtime_config.verbose:
            raise

        terminate(1)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        terminate()
