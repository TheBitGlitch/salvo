# Copyright (c) 2026 TheBitGlitch
# SPDX-License-Identifier: MIT

import sys
import socket

from cli import app
from cli.sub_apps import RuntimeArgs
from cli.helpers import get_invocation

from kernel.core import Engine
from kernel.api import ApiFactory
from kernel.api.exceptions import ApiError
from kernel.libs.printer import Console

from tools.history import History


def check_network_access(timeout: float = 10) -> bool:
    """Checks whether a network connection can be established."""

    try:
        with socket.create_connection(address=("8.8.8.8", 53), timeout=timeout):
            return True

    except OSError:
        return False


def graceful_exit(status: int = 0) -> None:
    """Exits the program with the specified status code."""
    sys.exit(status)


def main() -> None:
    HISTORY_BLACK_LIST = ("manage history",)

    if invocation := get_invocation(HISTORY_BLACK_LIST):
        History.add(invocation)

    # Management commands complete their work without producing runtime arguments.
    runtime_args: RuntimeArgs | None = app()

    if runtime_args is None:
        graceful_exit()  # No runtime execution is required.

    console = Console()

    if not check_network_access():
        console.error(
            "No network connection found. Please check your internet and try again."
        )
        graceful_exit(1)

    try:
        api_factory = ApiFactory(
            endpoints_path=runtime_args.endpoints,
            context={"phone": runtime_args.target},
        )
        api_factory.build()

        console.notice(
            f"Loaded {api_factory.slot_count} valid API endpoints successfully."
        )

    except ApiError as exc:
        console.error(str(exc))
        graceful_exit(1)

    if runtime_args.proxy is None:
        confirm_continue = console.input(
            "No proxy configured. Continue with your own IP address? (y/n): "
        ).lower()

        if confirm_continue not in ("y", "yes"):
            console.notice("Mission aborted by operator.")
            graceful_exit()

    console.clear_screen()

    try:
        engine = Engine(
            api_slots=api_factory.api_slots,
            runtime_args=runtime_args,
            console=console,
        )
        engine.launch()

    except Exception as exc:
        console.error(f"Unexpected error: {str(exc)}")
        graceful_exit(1)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        graceful_exit()
