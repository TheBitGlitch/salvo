import sys
import asyncio
import ctypes as ct
from pathlib import Path
from datetime import datetime
from typing import Any, TextIO
from dataclasses import dataclass
from collections.abc import Sequence

from .color import Color
from .tags import Tag, SeverityTag, EventTag, SystemTag, ResponseTag


@dataclass(frozen=True, slots=True)
class LogRecord:
    """
    Represent structured log data and its formatting options.

    Attributes:
        tags: One or more tags describing the log entry.
        message: Main log message.
        payloads: Additional key-value data attached to the log entry.
        color: Color used to render the log entry.
        stream: Output stream associated with the log entry.
        log_id: Optional identifier displayed with the log entry.
        include_time: Whether to include a timestamp in the formatted output.
        payloads_include_none: Whether payloads with None values are included.
    """

    tags: Tag | Sequence[Tag]
    message: str
    payloads: dict[str, Any]
    color: Color
    stream: TextIO

    log_id: int | None = None
    include_time: bool = True
    payloads_include_none: bool = True


@dataclass(frozen=True, slots=True)
class LogEntry:
    """
    Represent a log message ready for output.

    Attributes:
        content: Complete log message ready to be written.
        stream: Output stream associated with the log message.
    """

    content: str
    stream: TextIO


class Console:
    """
    Provide colored console output, structured logging, and asynchronous log handling.

    The console supports timestamped messages, severity and event tags,
    formatted payloads, colored output, and separate stdout/stderr streams.
    Logging can be performed synchronously or through a background asyncio
    task backed by a bounded queue.

    Application logs are written to `stderr` while response output is written
    to `stdout`, allowing command results to be captured independently from
    application diagnostics.

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
    def _print(text: str, stream: TextIO, end: str = "\n", flush: bool = False) -> None:
        """
        Write a string directly to the specified output stream.

        Args:
            text: Text to write to the output stream.
            stream: Output stream to write to.
            end: String appended to the output.
            flush: Whether to flush the output stream immediately.
        """
        stream.write(f"{text}{end}")

        if flush:
            stream.flush()

    def clear_screen(self) -> None:
        """Clear the terminal screen and move the cursor to the home position."""
        self._print(text="\033[H\033[J", stream=sys.stdout, end="", flush=True)

    def __init__(
        self,
        verbose: bool = False,
        colored: bool = True,
        time_format: str = "%H:%M:%S",
        payload_open: str = "<",
        payload_close: str = ">",
    ) -> None:
        """
        Initialize the console logger.

        Args:
            verbose: Whether optional DEBUG-level log messages are enabled.
                When disabled, calls to `Console.debug()` are ignored.
            colored: Whether console output uses ANSI color codes.
            time_format: Time-stamp format passed to `datetime.strftime()`.
            payload_open: Opening delimiter used when formatting payloads.
            payload_close: Closing delimiter used when formatting payloads.

        Internal state:
            _log_queue: Bounded queue containing pending log entries.
            _log_task: Background asyncio task responsible for draining
                the log queue, or `None` when the logger is not running.
            _dropped_log_count: Number of log entries discarded because
                the log queue was full.
        """
        if colored:
            self._enable_ansi_support()

        self._verbose = verbose
        self._colored = colored
        self._time_format = time_format
        self._payload_open = payload_open
        self._payload_close = payload_close

        self._log_queue: asyncio.Queue[LogEntry | None] = asyncio.Queue(maxsize=1000)
        self._log_task: asyncio.Task[None] | None = None
        self._log_lock: asyncio.Lock = asyncio.Lock()

        self._dropped_log_count = 0

    @property
    def dropped_log_count(self) -> int:
        """Return the number of log entries dropped because the queue was full."""
        return self._dropped_log_count

    def _paint(self, text: str, color: Color) -> str:
        """Apply the given ANSI color to `text` when `_colored` is enabled."""
        if not self._colored:
            return text

        return f"{color}{text}{Color.RESET}"

    def _format_time(self, include_time: bool) -> str:
        """
        Return the current timestamp formatted using the configured time format.

        If timestamping is disabled or format string is empty, returns an empty string.
        """
        if not include_time or not self._time_format:
            return ""

        return datetime.now().strftime(self._time_format)

    def _format_tags(self, tags: Tag | Sequence[Tag]) -> str:
        """
        Format one or more tags into a single string.

        Each tag is rendered using its string representation and enclosed
        in square brackets.

        Example:
            (NOTICE, JAILED) -> "[NOTICE] [JAILED]"

        Args:
            tags: A single tag or a sequence of console, system, event,
                or response tags.

        Returns:
            Formatted tag string, or an empty string if no tags are provided.
        """
        if isinstance(tags, Tag):
            tags = (tags,)

        return " ".join(f"[{tag}]" for tag in tags)

    def _format_payloads(
        self, payloads: dict[str, Any], include_none_values: bool
    ) -> str:
        """
        Format payload data as a delimited key-value string.

        Args:
            payloads: Key-value pairs to display.
            include_none_values: Whether entries with `None` values should be included.

        Returns:
            A formatted payload string, or an empty string when there is no
            payload data to display.
        """
        if not payloads:
            return ""

        if not include_none_values:
            payloads = {
                key: value for key, value in payloads.items() if value is not None
            }

        if not payloads:
            return ""

        formatted = ", ".join(f"{key}: {value}" for key, value in payloads.items())
        return f"{self._payload_open}{formatted}{self._payload_close}"

    def _format_log(self, log_record: LogRecord) -> LogEntry:
        """
        Format a log record into a complete log entry.

        Combines the timestamp, log identifier, tags, message, and payloads,
        then applies the configured color and preserves the output stream.

        Args:
            log_record: Structured log data and formatting options.

        Returns:
            Formatted log entry with its associated output stream.
        """
        log_id = f"[{log_record.log_id:02d}]" if log_record.log_id is not None else None

        components = (
            self._format_time(log_record.include_time),
            log_id,
            self._format_tags(log_record.tags),
            log_record.message,
            self._format_payloads(
                log_record.payloads, log_record.payloads_include_none
            ),
        )

        return LogEntry(
            content=self._paint(
                " ".join(filter(None, components)),
                log_record.color,
            ),
            stream=log_record.stream,
        )

    async def _logger_drain(self) -> None:
        """
        Continuously consume log entries from the queue and write them
        to their associated output streams.

        The logger stops when it receives a `None` sentinel. Each queue
        entry is marked as processed after it has been handled.
        """
        while True:
            log_entry: LogEntry | None = await self._log_queue.get()

            try:
                if log_entry is None:
                    break

                self._print(text=log_entry.content, stream=log_entry.stream)

            except (OSError, ValueError):
                self._dropped_log_count += 1

            finally:
                self._log_queue.task_done()

    def _emit(self, log_record: LogRecord) -> None:
        """
        Format and emit a log record.

        Writes the formatted entry directly to its output stream when the
        background logger is inactive. Otherwise, queues the entry for
        asynchronous processing.

        If the queue is full, the entry is discarded and the dropped log
        counter is incremented.

        Args:
            log_record: Structured log data and formatting options.
        """
        log_entry = self._format_log(log_record)

        if self._log_task is not None and not self._log_task.done():
            try:
                self._log_queue.put_nowait(log_entry)

            except asyncio.QueueFull:
                self._dropped_log_count += 1

            return

        self._print(text=log_entry.content, stream=log_entry.stream, flush=True)

    async def start_logger(self) -> None:
        """
        Start the background log-drain task.

        Creates an `asyncio.Task` that continuously consumes queued log
        entries and writes them to their associated output streams.

        If the logger is already running, this method does nothing.

        Raises:
            RuntimeError: If called without a running event loop.
        """
        async with self._log_lock:
            if self._log_task is not None and not self._log_task.done():
                return

            self._log_task = asyncio.create_task(self._logger_drain())

    async def stop_logger(self) -> None:
        """
        Gracefully stop the background log-drain task.

        A sentinel is placed in the queue so that all previously queued
        log entries are processed before the logger exits.

        If the logger is not running, this method does nothing.
        """
        async with self._log_lock:
            task = self._log_task

            if task is None:
                return

            if not task.done():
                await self._log_queue.put(None)

            try:
                await task

            finally:
                self._log_task = None

    def input(
        self, prompt: str, color: Color = Color.SKY_BLUE, include_time: bool = True
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
        components = (
            self._format_time(include_time=include_time),
            prompt,
        )
        colored_prompt = self._paint(" ".join(filter(None, components)), color)

        return input(colored_prompt).strip()

    def event(
        self, severity: SeverityTag, event_type: EventTag, message: str, **payloads: Any
    ) -> None:
        """
        Emit a structured event log with severity and event tags.

        Events represent application lifecycle and state changes.

        Example:
            12:34:56 [NOTICE] [FREED] API has been freed.

        Args:
            severity: Log severity level, such as `NOTICE` or `WARNING`.
            event_type: Event type, such as `JAILED` or `FREED`.
            message: Main log message.
            payloads: Optional payload data attached to the event.
        """
        self._emit(
            LogRecord(
                tags=(
                    severity,
                    event_type,
                ),
                message=message,
                payloads=payloads,
                color=event_type.color,
                stream=sys.stderr,
            )
        )

    def debug(self, message: str, **payloads: Any) -> None:
        """
        Emit an optional DEBUG-level log.

        DEBUG messages are intended for diagnostic information that is useful
        during development or troubleshooting but is not normally shown to users.

        When verbose logging is disabled, this method returns without emitting
        or queuing a log entry.

        Args:
            message: Debug message content.
            payloads: Optional payload data.
        """
        if not self._verbose:
            return

        tag = SeverityTag.DEBUG

        self._emit(
            LogRecord(
                tags=tag,
                message=message,
                payloads=payloads,
                color=tag.color,
                stream=sys.stderr,
            )
        )

    def notice(self, message: str, **payloads: Any) -> None:
        """
        Emit a NOTICE-level log.

        Used for general informational messages that are not warnings or errors.

        Args:
            message: Log message content.
            payloads: Optional payload data.
        """
        tag = SeverityTag.NOTICE

        self._emit(
            LogRecord(
                tags=tag,
                message=message,
                payloads=payloads,
                color=tag.color,
                stream=sys.stderr,
            )
        )

    def warning(self, message: str, **payloads: Any) -> None:
        """
        Emit a WARNING-level log.

        Used for potential issues that do not stop execution but may require
        attention.

        Args:
            message: Log message content.
            payloads: Optional payload data.
        """
        tag = SeverityTag.WARNING

        self._emit(
            LogRecord(
                tags=tag,
                message=message,
                payloads=payloads,
                color=tag.color,
                stream=sys.stderr,
            )
        )

    def critical(self, message: str, **payloads: Any) -> None:
        """
        Emit a CRITICAL-level log.

        Used for severe errors that indicate system instability or failure
        conditions.

        Args:
            message: Log message content.
            payloads: Optional payload data.
        """
        tag = SeverityTag.CRITICAL

        self._emit(
            LogRecord(
                tags=tag,
                message=message,
                payloads=payloads,
                color=tag.color,
                stream=sys.stderr,
            )
        )

    def error(self, message: str, **payloads: Any) -> None:
        """
        Emit an ERROR-level log.

        Used when an operation fails but the system can continue running.

        Args:
            message: Log message content.
            payloads: Optional payload data.
        """
        tag = SeverityTag.ERROR

        self._emit(
            LogRecord(
                tags=tag,
                message=message,
                payloads=payloads,
                color=tag.color,
                stream=sys.stderr,
            )
        )

    def response(
        self, request_id: int, response_tag: ResponseTag, source: str, **payloads: Any
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
            response_tag: Response status.
            source: API source name.
            payloads: Additional response payload to include in the log.
        """
        self._emit(
            LogRecord(
                tags=response_tag,
                message=source,
                payloads=payloads,
                color=response_tag.color,
                stream=sys.stdout,
                payloads_include_none=False,
                log_id=request_id,
            )
        )

    def manifest(self, config: dict[str, Any]) -> None:
        """
        Emit the application configuration as a compact and multi-line manifest.

        Configuration entries retain their original order and are distributed
        across multiple log lines.

        Args:
            config: Application configuration key-value pairs to display.
        """
        if not config:
            return

        endpoints_path = config["endpoints"]

        if len(endpoints_path.parts) > 4:
            endpoints_path = Path("...", *endpoints_path.parts[-4:])

        ssl_enabled = "ON" if config["ssl"] else "OFF"
        fallback_enabled = "ON" if config["fallback"] else "OFF"
        proxy = config["proxy"]

        manifest_lines = [
            f"Target: {config['target']} | Mode: {config['mode'].value.upper()}",
            f"Limit: {config['limit']} | Fail-Tolerance: {config['fail_tolerance']} | Concurrency: {config['concurrency']}",
            (
                f"Timeout: {config['timeout']}s | Proxy: None | SSL: {ssl_enabled} | Fallback: {fallback_enabled}"
                if proxy is None
                else f"Timeout: {config['timeout']}s | Proxy: {proxy}"
            ),
            *(
                []
                if proxy is None
                else [f"SSL: {ssl_enabled} | Fallback: {fallback_enabled}"]
            ),
            f"Endpoints: {str(endpoints_path)}",
            f"Color: {'ON' if config['color'] else 'OFF'} | Verbose: {'ON' if config['verbose'] else 'OFF'}",
        ]

        tag = SystemTag.MANIFEST

        for line in manifest_lines:
            self._emit(
                LogRecord(
                    tags=tag,
                    message=line,
                    payloads={},
                    color=tag.color,
                    stream=sys.stderr,
                )
            )

    def summary(
        self, success_count: int, failure_count: int, duration_seconds: float
    ) -> None:
        """
        Emit a final aggregated summary of system execution in multiple lines.

        The summary includes the total number of operations, successful and
        failed operations, success rate, total execution seconds, and the number
        of logs dropped because the asynchronous queue was full.

        Args:
            success_count: Number of successful operations.
            failure_count: Number of failed operations.
            duration_seconds: Total execution time in seconds.
        """
        total_count = success_count + failure_count
        success_rate = success_count / total_count * 100 if total_count else 0.0

        summary_lines = (
            f"Total: {total_count} | Success: {success_count} | Failure: {failure_count}",
            f"Success Rate: {success_rate:.1f}% | Duration: {duration_seconds:.1f}s | "
            f"Dropped Logs: {self._dropped_log_count}",
        )

        tag = SystemTag.SUMMARY

        for line in summary_lines:
            self._emit(
                LogRecord(
                    tags=tag,
                    message=line,
                    payloads={},
                    color=tag.color,
                    stream=sys.stderr,
                )
            )
