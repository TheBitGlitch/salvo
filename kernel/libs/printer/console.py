import sys
import asyncio
import ctypes as ct
from datetime import datetime
from typing import Any, TextIO
from dataclasses import dataclass
from collections.abc import Sequence

from .color import Color
from .tags import Tag, SeverityTag, EventTag, SystemTag, ResponseTag


@dataclass(frozen=True, slots=True)
class LogEntry:
    log: str
    stream: TextIO


class Console:
    """
    Provide colored console output, structured logging, and asynchronous log handling.

    The console supports timestamped messages, severity and event tags,
    formatted payloads, colored output, and separate stdout/stderr streams.
    Logging can be performed synchronously or through a background asyncio
    task backed by a bounded queue.

    The logger also tracks the number of log entries dropped when the
    asynchronous queue is full.
    """

    @staticmethod
    def _enable_ansi_support() -> None:
        """
        Enable ANSI escape code processing on Windows terminals.

        Uses the Windows Console API to enable virtual terminal
        processing. On non-Windows systems, this is a no-op.
        """
        if sys.platform != "win32":
            return

        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        try:
            kernel32 = ct.windll.kernel32
            handle = kernel32.getStdHandle(STD_OUTPUT_HANDLE)

            if handle == -1:
                return

            mode = ct.c_ulong()

            if not kernel32.GetConsoleMode(handle, ct.byref(mode)):
                return

            mode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)

        except Exception:
            return

    @staticmethod
    def _print(
        string: str, stream: TextIO, end: str = "\n", flush: bool = False
    ) -> None:
        """
        Write a string directly to the specified output stream.

        Args:
            string: Text to write to the output stream.
            stream: Output stream to write to.
            end: String appended to the output.
            flush: Whether to flush the output stream immediately.
        """
        stream.write(f"{string}{end}")

        if flush:
            stream.flush()

    def clear_screen(self) -> None:
        """Clear the terminal screen and move the cursor to the home position."""
        self._print("\033[H\033[J", stream=sys.stdout, end="", flush=True)

    def __init__(
        self,
        time_format: str = "%H:%M:%S",
        payload_open: str = "<",
        payload_close: str = ">",
    ) -> None:
        """
        Initialize the console logger.

        Args:
            time_format: Time-stamp format passed to `datetime.strftime()`.
            payload_open: Opening delimiter used when formatting payloads.
            payload_close: Closing delimiter used when formatting payloads.

        Internal state:
            _time_format: Configured timestamp format.
            _payload_open: Opening delimiter for formatted payloads.
            _payload_close: Closing delimiter for formatted payloads.
            _log_queue: Bounded queue containing pending log entries.
            _log_task: Background asyncio task responsible for draining
                the log queue, or `None` when the logger is not running.
            _dropped_log_count: Number of log entries discarded because
                the log queue was full.
        """
        self._enable_ansi_support()

        self._time_format = time_format
        self._payload_open = payload_open
        self._payload_close = payload_close

        self._log_queue: asyncio.Queue[LogEntry | None] = asyncio.Queue(maxsize=1000)
        self._log_task: asyncio.Task[None] | None = None

        self._dropped_log_count = 0

    @property
    def dropped_log_count(self) -> int:
        """Return the number of log entries dropped because the queue was full."""
        return self._dropped_log_count

    def _apply_color(self, string: str, color: Color) -> str:
        """Wrap ``string`` with the given ANSI color and a reset code."""
        return f"{color}{string}{Color.RESET}"

    def _format_time(self, include_time: bool) -> str:
        """
        Return the current timestamp formatted using the configured time format.

        If timestamping is disabled or format string is empty, returns an empty string.
        """
        if not include_time or not self._time_format:
            return ""

        return datetime.now().strftime(self._time_format)

    def _format_payloads(self, payloads: dict[str, Any], include_none: bool) -> str:
        """
        Format payload data as a delimited key-value string.

        Args:
            payloads: Key-value pairs to display.
            include_none: Whether entries with `None` values should be included.

        Returns:
            A formatted payload string, or an empty string when there is no
            payload data to display.
        """
        if not payloads:
            return ""

        if not include_none:
            payloads = {k: v for k, v in payloads.items() if v is not None}

        if not payloads:
            return ""

        formatted = ", ".join(f"{k}: {v}" for k, v in payloads.items())
        return f"{self._payload_open}{formatted}{self._payload_close}"

    def _format_tags(self, tags: Sequence[Tag]) -> str:
        """
        Format a sequence of tags into a single string.

        Each tag is rendered using its string representation and wrapped
        in square brackets.

        Example:
            (NOTICE, JAILED) -> "[NOTICE] [JAILED]"

        Args:
            tags: Sequence of console, system, event or response tags.

        Returns:
            Formatted tag string or an empty string if no tags are provided.
        """
        if not tags:
            return ""

        return " ".join(f"[{t}]" for t in tags)

    async def _logger_drain(self) -> None:
        """
        Continuously consume log entries from the queue and write them
        to their associated output streams.

        The logger stops when it receives a `None` sentinel. Each queue
        entry is marked as processed after it has been handled.
        """
        while True:
            entry = await self._log_queue.get()

            try:
                if entry is None:
                    break

                self._print(string=entry.log, stream=entry.stream)

            finally:
                self._log_queue.task_done()

    def _emit(
        self,
        tags: Sequence[Tag],
        message: str,
        payloads: dict[str, Any],
        color: Color,
        stream: TextIO,
        include_time: bool = True,
        include_none: bool = True,
        log_id: int | None = None,
    ) -> None:
        """
        Format and emit a log message.

        If the background logger is running, the formatted entry is queued
        for asynchronous output. Otherwise, it is written directly to the
        specified stream.

        Entries are dropped when the asynchronous log queue is full.

        Args:
            tags: Tags describing the type or severity of the log.
            message: Main log message.
            payloads: Additional key-value data to include in the log.
            color: ANSI color applied to the complete formatted log.
            stream: Output stream where the log should be written.
            include_time: Whether to include a timestamp.
            include_none: Whether payload entries with `None` values are included.
            log_id: Optional numeric identifier displayed as a zero-padded value.
        """
        log_id = f"{log_id:02d}" if log_id is not None else None

        log_parts = (
            self._format_time(include_time=include_time),
            log_id,
            self._format_tags(tags),
            message,
            self._format_payloads(payloads=payloads, include_none=include_none),
        )

        formatted_log = " ".join(filter(None, log_parts))
        log = self._apply_color(formatted_log, color)

        if self._log_task is not None and not self._log_task.done():
            try:
                self._log_queue.put_nowait(LogEntry(log=log, stream=stream))

            except asyncio.QueueFull:
                self._dropped_log_count += 1

        else:
            self._print(string=log, stream=stream, flush=True)

    def start_logger(self) -> None:
        """
        Start the background log-drain task.

        Creates an `asyncio.Task` that continuously consumes queued log
        entries and writes them to their associated output streams.

        If the logger is already running, this method does nothing.

        Raises:
            RuntimeError: If called without a running event loop.
        """
        if self._log_task is None or self._log_task.done():
            self._log_task = asyncio.create_task(self._logger_drain())

    async def stop_logger(self) -> None:
        """
        Gracefully stop the background log-drain task.

        A sentinel is placed in the queue so that all previously queued
        log entries are processed before the logger exits.

        If the logger is not running, this method does nothing.
        """
        if self._log_task is not None:
            await self._log_queue.put(None)
            await self._log_task

            self._log_task = None

    def input(
        self, prompt: str, color: Color = Color.LIGHT_CYAN, include_time: bool = True
    ) -> str:
        """
        Display a colored prompt and wait for user input.

        Args:
            prompt: Text shown to the user.
            color: ANSI color for the prompt.
            include_time: Whether to include a timestamp.

        Returns:
            Stripped user input.
        """
        prompt_parts = (
            self._format_time(include_time=include_time),
            prompt,
        )
        formatted_prompt = " ".join(filter(None, prompt_parts))
        colored_prompt = self._apply_color(formatted_prompt, color)

        return input(colored_prompt).strip()

    def event(
        self, severity: SeverityTag, event: EventTag, message: str, **kwargs
    ) -> None:
        """
        Emit a structured event log with severity and event tags.

        Events represent application lifecycle and state changes.

        Example:
            12:34:56 [NOTICE] [FREED] API has been freed.

        Args:
            severity: Log severity level, such as `NOTICE` or `WARNING`.
            event: Event type, such as `JAILED` or `FREED`.
            message: Main log message.
            kwargs: Optional payload data attached to the event.
        """
        self._emit(
            tags=(
                severity,
                event,
            ),
            message=message,
            payloads=kwargs,
            color=event.color,
            stream=sys.stdout,
        )

    def notice(self, message: str, **kwargs) -> None:
        """
        Emit a NOTICE-level log.

        Used for general informational messages that are not warnings or errors.

        Args:
            message: Log message content.
            kwargs: Optional payload data.
        """
        tag = SeverityTag.NOTICE

        self._emit(
            tags=(tag,),
            message=message,
            payloads=kwargs,
            color=tag.color,
            stream=sys.stdout,
        )

    def warning(self, message: str, **kwargs) -> None:
        """
        Emit a WARNING-level log.

        Used for potential issues that do not stop execution but may require
        attention.

        Args:
            message: Log message content.
            kwargs: Optional payload data.
        """
        tag = SeverityTag.WARNING

        self._emit(
            tags=(tag,),
            message=message,
            payloads=kwargs,
            color=tag.color,
            stream=sys.stdout,
        )

    def critical(self, message: str, **kwargs) -> None:
        """
        Emit a CRITICAL-level log.

        Used for severe errors that indicate system instability or failure
        conditions.

        Args:
            message: Log message content.
            kwargs: Optional payload data.
        """
        tag = SeverityTag.CRITICAL

        self._emit(
            tags=(tag,),
            message=message,
            payloads=kwargs,
            color=tag.color,
            stream=sys.stderr,
        )

    def error(self, message: str, **kwargs) -> None:
        """
        Emit an ERROR-level log.

        Used when an operation fails but the system can continue running.

        Args:
            message: Log message content.
            kwargs: Optional payload data.
        """
        tag = SeverityTag.ERROR

        self._emit(
            tags=(tag,),
            message=message,
            payloads=kwargs,
            color=tag.color,
            stream=sys.stderr,
        )

    def response(
        self, request_id: int, tag: ResponseTag, source: str, **kwargs
    ) -> None:
        """
        Emit a structured response log for an API request.

        This is typically used to log request results with status tracking.

        Example:
        12:34:56 [01] [SUCCESS] example.com <status_code: 200>
        12:34:57 [02] [FAILURE] sample.com <status_code: 429>
        12:34:59 [03] [ZOMBIE] example.com <status_code: 200>

        Args:
            request_id: Request or correlation identifier.
            tag: Response status.
            source: API source name.
            kwargs: Additional response payload to include in the log.
        """
        self._emit(
            tags=(tag,),
            message=source,
            payloads=kwargs,
            color=tag.color,
            stream=sys.stdout,
            include_none=False,
            log_id=request_id,
        )

    def summary(self, success: int, failure: int, total_time: float) -> None:
        """
        Emit a final aggregated summary of system execution.

        The summary includes the total number of operations, successful and
        failed operations, success rate, total execution time, and the number
        of logs dropped because the asynchronous queue was full.

        Args:
            success: Number of successful operations.
            failure: Number of failed operations.
            total_time: Total execution time in seconds.
        """
        total = success + failure
        rate = (success / total) * 100 if total != 0 else 0.0

        message = (
            f"Time: {total_time:.1f}s | "
            f"Total: {total} | Success: {success} | "
            f"Failure: {failure} | Success Rate: {rate:.1f}%"
        )
        tag = SystemTag.SUMMARY

        self._emit(
            tags=(tag,),
            message=message,
            payloads={"dropped_logs": self._dropped_log_count},
            color=tag.color,
            stream=sys.stdout,
        )
