import pydoc
from pathlib import Path
from typing import Annotated
from datetime import datetime

from cyclopts.validators import Number
from cyclopts.parameter import Parameter

from default_path import DefaultPath


class History:
    """Manages the application's history."""

    _PATH = DefaultPath.HISTORY
    _MAX_SIZE = 5 * 1024 * 1024

    @staticmethod
    def _time_stamp() -> str:
        return datetime.now().strftime("%d/%m %H:%M:%S")

    @staticmethod
    def _tail(path: Path, n: int, reverse: bool = False, chunk_size: int = 8192) -> str:
        """
        Reads the last `n` lines from a file without loading the entire
        file into memory.

        Args:
            path: Path to the file.
            n: Number of lines to read.
            reverse: Whether to return the lines in reverse order.
            chunk_size: Number of bytes to read per iteration.

        Returns:
            The last `n` lines of the file, optionally in reverse order.
        """
        if n < 1:
            return ""

        with path.open("rb") as f:
            f.seek(0, 2)
            position = f.tell()

            buffer = b""

            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size

                f.seek(position)

                buffer = f.read(read_size) + buffer

                if buffer.count(b"\n") >= n:
                    break

        lines = buffer.splitlines()

        if not lines:
            return ""

        lines = lines[-n:]

        if reverse:
            lines = lines[::-1]

        return b"\n".join(lines).decode("utf-8") + "\n"

    @classmethod
    def _trim_if_oversized(cls) -> None:
        """
        Trims the history file when its size exceeds the maximum limit of 5 MiB.

        The oldest half of the entries is removed, retaining the most recent
        entries.
        """
        if cls._PATH.stat().st_size <= cls._MAX_SIZE:
            return

        with cls._PATH.open("rb") as f:
            line_count = sum(1 for _ in f)

        keep_lines = max(1, line_count // 2)
        records = cls._tail(cls._PATH, n=keep_lines)

        temp_path = cls._PATH.with_suffix(cls._PATH.suffix + ".tmp")
        temp_path.write_text(records, encoding="utf-8")
        temp_path.replace(cls._PATH)

    @classmethod
    def add(cls, command: str) -> None:
        cls._PATH.parent.mkdir(exist_ok=True, parents=True)

        record = f"{cls._time_stamp()} - {command}\n"

        with cls._PATH.open("a", encoding="utf-8") as f:
            f.write(record)

        cls._trim_if_oversized()

    def show(self, n: int) -> None:
        """
        Displays the `n` most recent history entries.

        Args:
            n: Number of recent entries to display.
        """
        try:
            records = self._tail(self._PATH, n=n, reverse=True)

        except FileNotFoundError:
            records = ""

        if not records:
            print("No history available.")
            return

        pager = pydoc.get_pager()
        pager(records)

    def clear(self) -> None:
        """Removes the history file."""
        self._PATH.unlink(missing_ok=True)


def history(
    number: Annotated[
        int,
        Parameter(
            name=["-n", "--number"],
            validator=Number(gte=1),
            help="Number of recent history entries to display.",
        ),
    ] = 20,
    clear: Annotated[
        bool,
        Parameter(
            name=["-c", "--clear"],
            help="Clear the history.",
        ),
    ] = False,
) -> None:
    """
    Manage the history.

    Args:
        n: Number of recent history entries to display.
        clear: Whether to clear the history instead of displaying it.
    """
    _history = History()

    if clear:
        _history.clear()
        print("History cleared successfully.")
        return

    _history.show(n=number)


# CLI entry point for this tool; used by the manage subcommand for automatic discovery.
COMMAND = history
