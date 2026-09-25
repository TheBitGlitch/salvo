"""
Full pytest test suite for mypkg.console.Console.

Notes on approach:
- Public logging methods (notice/warning/critical/error/event/response/summary)
  are tested two ways:
    1. Dispatch tests that patch `_emit` and assert it is called with the
       correct tags/message/payloads/color/stream, isolating each method's
       own logic from `_emit`'s formatting/queueing internals.
    2. A couple of integration tests that let `_emit` run for real and check
       the actual text written to stdout/stderr, so the wiring between the
       two layers is also covered.
- Async behavior (start_logger/stop_logger/_logger_drain and the queueing
  branch of `_emit`) is tested with `pytest.mark.asyncio`.
- Timestamps are made deterministic by monkeypatching `console.datetime`
  with a subclass whose `now()` returns a fixed value.
"""

import asyncio
import io
import sys
from unittest.mock import MagicMock, patch

import pytest

import kernel.libs.printer.console as console_module
from kernel.libs.printer import Color
from kernel.libs.printer.console import Console, LogEntry
from kernel.libs.printer.tags import SeverityTag, EventTag, SystemTag, ResponseTag


@pytest.fixture
def console() -> Console:
    return Console()


@pytest.fixture
def stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def frozen_time(monkeypatch):
    """Make `_format_time` deterministic by freezing `datetime.now()`."""

    from datetime import datetime as real_datetime

    fixed = real_datetime(2024, 1, 1, 12, 34, 56)

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(console_module, "datetime", FrozenDateTime)
    return fixed.strftime("%H:%M:%S")


class TestInit:
    def test_defaults(self, console: Console):
        assert console._time_format == "%H:%M:%S"
        assert console._payload_open == "<"
        assert console._payload_close == ">"
        assert console._log_task is None
        assert console.dropped_log_count == 0
        assert isinstance(console._log_queue, asyncio.Queue)
        assert console._log_queue.maxsize == 1000

    def test_custom_params(self):
        console = Console(time_format="%Y", payload_open="[", payload_close="]")
        assert console._time_format == "%Y"
        assert console._payload_open == "["
        assert console._payload_close == "]"

    def test_dropped_log_count_is_read_only_property(self, console: Console):
        with pytest.raises(AttributeError):
            console.dropped_log_count = 5  # type: ignore[misc]


class TestEnableAnsiSupport:
    def test_noop_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(console_module.sys, "platform", "linux")
        # Should simply return without touching ctypes at all.
        Console._enable_ansi_support()

    def test_enables_virtual_terminal_processing_on_windows(self, monkeypatch):
        monkeypatch.setattr(console_module.sys, "platform", "win32")

        kernel32 = MagicMock()
        kernel32.getStdHandle.return_value = 7
        kernel32.GetConsoleMode.return_value = 1

        monkeypatch.setattr(
            console_module.ct, "windll", MagicMock(kernel32=kernel32), raising=False
        )

        Console._enable_ansi_support()

        kernel32.getStdHandle.assert_called_once_with(-11)
        kernel32.GetConsoleMode.assert_called_once()
        assert kernel32.SetConsoleMode.called
        handle_arg, mode_arg = kernel32.SetConsoleMode.call_args[0]
        assert handle_arg == 7
        assert mode_arg.value == 0x0004

    def test_returns_early_on_invalid_handle(self, monkeypatch):
        monkeypatch.setattr(console_module.sys, "platform", "win32")

        kernel32 = MagicMock()
        kernel32.getStdHandle.return_value = -1

        monkeypatch.setattr(
            console_module.ct, "windll", MagicMock(kernel32=kernel32), raising=False
        )

        Console._enable_ansi_support()

        kernel32.GetConsoleMode.assert_not_called()
        kernel32.SetConsoleMode.assert_not_called()

    def test_returns_early_when_get_console_mode_fails(self, monkeypatch):
        monkeypatch.setattr(console_module.sys, "platform", "win32")

        kernel32 = MagicMock()
        kernel32.getStdHandle.return_value = 7
        kernel32.GetConsoleMode.return_value = 0  # falsy => failure

        monkeypatch.setattr(
            console_module.ct, "windll", MagicMock(kernel32=kernel32), raising=False
        )

        Console._enable_ansi_support()

        kernel32.SetConsoleMode.assert_not_called()

    def test_swallows_unexpected_exceptions(self, monkeypatch):
        monkeypatch.setattr(console_module.sys, "platform", "win32")

        class ExplodingWindll:
            @property
            def kernel32(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            console_module.ct, "windll", ExplodingWindll(), raising=False
        )

        # Must not raise.
        Console._enable_ansi_support()

    def test_called_automatically_on_init(self):
        with patch.object(Console, "_enable_ansi_support") as spy:
            Console()
            spy.assert_called_once()


class TestPrint:
    def test_writes_string_with_default_newline(
        self, console: Console, stream: io.StringIO
    ):
        console._print("hello", stream=stream)
        assert stream.getvalue() == "hello\n"

    def test_writes_with_custom_end(self, console: Console, stream: io.StringIO):
        console._print("hello", stream=stream, end="")
        assert stream.getvalue() == "hello"

    def test_flush_true_flushes_stream(self, console: Console):
        fake_stream = MagicMock()
        console._print("hello", stream=fake_stream, flush=True)
        fake_stream.write.assert_called_once_with("hello\n")
        fake_stream.flush.assert_called_once()

    def test_flush_false_does_not_flush(self, console: Console):
        fake_stream = MagicMock()
        console._print("hello", stream=fake_stream, flush=False)
        fake_stream.flush.assert_not_called()


class TestClearScreen:
    def test_clears_screen_and_moves_cursor_home(self, monkeypatch, console: Console):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.clear_screen()

        assert fake_stdout.getvalue() == "\033[H\033[J"

    def test_flushes_stdout(self, monkeypatch, console: Console):
        fake_stdout = MagicMock()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.clear_screen()

        fake_stdout.flush.assert_called_once()


class TestApplyColor:
    def test_wraps_string_with_color_and_reset(self, console: Console):
        result = console._apply_color("hello", Color.RED)
        assert result == f"{Color.RED}hello{Color.RESET}"

    def test_empty_string(self, console: Console):
        result = console._apply_color("", Color.GREEN)
        assert result == f"{Color.GREEN}{Color.RESET}"


class TestFormatTime:
    def test_include_time_false_returns_empty(self, console: Console):
        assert console._format_time(include_time=False) == ""

    def test_empty_time_format_returns_empty(self):
        console = Console(time_format="")
        assert console._format_time(include_time=True) == ""

    def test_returns_formatted_timestamp(self, console: Console, frozen_time: str):
        assert console._format_time(include_time=True) == frozen_time

    def test_respects_custom_format(self, frozen_time: str):
        console = Console(time_format="%Y-%m-%d")
        assert console._format_time(include_time=True) == "2024-01-01"


class TestFormatPayloads:
    def test_empty_dict_returns_empty_string(self, console: Console):
        assert console._format_payloads({}, include_none=True) == ""

    def test_basic_formatting_with_delimiters(self, console: Console):
        result = console._format_payloads({"a": 1, "b": 2}, include_none=True)
        assert result == "<a: 1, b: 2>"

    def test_uses_custom_delimiters(self):
        console = Console(payload_open="[", payload_close="]")
        result = console._format_payloads({"a": 1}, include_none=True)
        assert result == "[a: 1]"

    def test_include_none_true_keeps_none_values(self, console: Console):
        result = console._format_payloads({"a": None}, include_none=True)
        assert result == "<a: None>"

    def test_include_none_false_filters_none_values(self, console: Console):
        result = console._format_payloads({"a": 1, "b": None}, include_none=False)
        assert result == "<a: 1>"

    def test_include_none_false_all_none_returns_empty(self, console: Console):
        result = console._format_payloads({"a": None, "b": None}, include_none=False)
        assert result == ""

    def test_preserves_insertion_order(self, console: Console):
        result = console._format_payloads({"z": 1, "a": 2}, include_none=True)
        assert result == "<z: 1, a: 2>"


class TestFormatTags:
    def test_empty_sequence_returns_empty_string(self, console: Console):
        assert console._format_tags(()) == ""

    def test_single_tag(self, console: Console):
        assert console._format_tags((SeverityTag.NOTICE,)) == "[NOTICE]"

    def test_multiple_tags_joined_with_space(self, console: Console):
        result = console._format_tags((SeverityTag.NOTICE, EventTag.FREED))
        assert result == "[NOTICE] [FREED]"

    def test_mixed_tag_types(self, console: Console):
        result = console._format_tags((SystemTag.SUMMARY, ResponseTag.SUCCESS))
        assert result == "[SUMMARY] [SUCCESS]"


class TestEmitSync:
    def test_writes_directly_when_no_logger_task(
        self, console: Console, stream: io.StringIO, frozen_time: str
    ):
        console._emit(
            tags=(SeverityTag.NOTICE,),
            message="hello",
            payloads={},
            color=Color.CYAN,
            stream=stream,
        )
        output = stream.getvalue()
        assert output == f"{Color.CYAN}{frozen_time} [NOTICE] hello{Color.RESET}\n"

    def test_includes_payloads(self, console: Console, stream: io.StringIO):
        console._emit(
            tags=(),
            message="hi",
            payloads={"x": 1},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        assert stream.getvalue() == f"{Color.RED}hi <x: 1>{Color.RESET}\n"

    def test_include_time_false_omits_timestamp(
        self, console: Console, stream: io.StringIO
    ):
        console._emit(
            tags=(),
            message="hi",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        assert stream.getvalue() == f"{Color.RED}hi{Color.RESET}\n"

    def test_log_id_is_zero_padded(self, console: Console, stream: io.StringIO):
        console._emit(
            tags=(),
            message="m",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
            log_id=5,
        )
        assert stream.getvalue() == f"{Color.RED}05 m{Color.RESET}\n"

    def test_log_id_none_is_omitted(self, console: Console, stream: io.StringIO):
        console._emit(
            tags=(),
            message="m",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
            log_id=None,
        )
        assert stream.getvalue() == f"{Color.RED}m{Color.RESET}\n"

    def test_include_none_false_passed_through_to_payloads(
        self, console: Console, stream: io.StringIO
    ):
        console._emit(
            tags=(),
            message="m",
            payloads={"a": None},
            color=Color.RED,
            stream=stream,
            include_time=False,
            include_none=False,
        )
        assert stream.getvalue() == f"{Color.RED}m{Color.RESET}\n"

    def test_flushes_the_stream(self, console: Console):
        fake_stream = MagicMock()
        console._emit(
            tags=(),
            message="m",
            payloads={},
            color=Color.RED,
            stream=fake_stream,
            include_time=False,
        )
        fake_stream.flush.assert_called_once()

    def test_does_not_touch_queue_when_no_task(
        self, console: Console, stream: io.StringIO
    ):
        console._emit(
            tags=(),
            message="m",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        assert console._log_queue.qsize() == 0

    def test_does_not_touch_queue_when_task_done(
        self, console: Console, stream: io.StringIO
    ):
        done_task = MagicMock()
        done_task.done.return_value = True
        console._log_task = done_task

        console._emit(
            tags=(),
            message="m",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )

        assert console._log_queue.qsize() == 0
        assert stream.getvalue() != ""


class TestEmitQueueing:
    def test_queues_instead_of_writing_when_task_running(
        self, console: Console, stream: io.StringIO
    ):
        running_task = MagicMock()
        running_task.done.return_value = False
        console._log_task = running_task

        console._emit(
            tags=(),
            message="queued",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )

        # Nothing written synchronously; the entry sits in the queue instead.
        assert stream.getvalue() == ""
        assert console._log_queue.qsize() == 1

        entry = console._log_queue.get_nowait()
        assert isinstance(entry, LogEntry)
        assert entry.stream is stream
        assert "queued" in entry.log

    def test_drops_entry_and_increments_counter_when_queue_full(
        self, console: Console, stream: io.StringIO
    ):
        console._log_queue = asyncio.Queue(maxsize=1)
        running_task = MagicMock()
        running_task.done.return_value = False
        console._log_task = running_task

        console._emit(
            tags=(),
            message="one",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        assert console.dropped_log_count == 0
        assert console._log_queue.qsize() == 1

        console._emit(
            tags=(),
            message="two",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        assert console.dropped_log_count == 1
        assert console._log_queue.qsize() == 1  # still just the first entry

        # The surviving entry in queue must be the first one, not the dropped one.
        entry = console._log_queue.get_nowait()
        assert "one" in entry.log


class TestLoggerDrain:
    @pytest.mark.asyncio
    async def test_consumes_entries_until_sentinel(
        self, console: Console, stream: io.StringIO
    ):
        await console._log_queue.put(LogEntry(log="first", stream=stream))
        await console._log_queue.put(LogEntry(log="second", stream=stream))
        await console._log_queue.put(None)  # sentinel

        await console._logger_drain()

        assert stream.getvalue() == "first\nsecond\n"
        assert console._log_queue.empty()

    @pytest.mark.asyncio
    async def test_stops_immediately_on_sentinel_only(self, console: Console):
        await console._log_queue.put(None)
        await console._logger_drain()  # should return promptly, no error

    @pytest.mark.asyncio
    async def test_routes_entries_to_their_own_streams(self, console: Console):
        stream_a = io.StringIO()
        stream_b = io.StringIO()
        await console._log_queue.put(LogEntry(log="to-a", stream=stream_a))
        await console._log_queue.put(LogEntry(log="to-b", stream=stream_b))
        await console._log_queue.put(None)

        await console._logger_drain()

        assert stream_a.getvalue() == "to-a\n"
        assert stream_b.getvalue() == "to-b\n"


class TestStartStopLogger:
    @pytest.mark.asyncio
    async def test_start_logger_creates_running_task(self, console: Console):
        console.start_logger()
        try:
            assert isinstance(console._log_task, asyncio.Task)
            assert not console._log_task.done()
        finally:
            await console.stop_logger()

    @pytest.mark.asyncio
    async def test_start_logger_is_idempotent_while_running(self, console: Console):
        console.start_logger()
        first_task = console._log_task
        console.start_logger()
        second_task = console._log_task
        try:
            assert first_task is second_task
        finally:
            await console.stop_logger()

    @pytest.mark.asyncio
    async def test_start_logger_replaces_a_finished_task(self, console: Console):
        console.start_logger()
        finished_task = console._log_task
        await console.stop_logger()
        assert finished_task.done()

        # Simulate a stale finished task reference and confirm a new one is created.
        console._log_task = finished_task
        console.start_logger()
        try:
            assert console._log_task is not finished_task
            assert not console._log_task.done()
        finally:
            await console.stop_logger()

    @pytest.mark.asyncio
    async def test_stop_logger_is_noop_when_not_running(self, console: Console):
        assert console._log_task is None
        await console.stop_logger()  # must not raise
        assert console._log_task is None

    @pytest.mark.asyncio
    async def test_stop_logger_resets_task_to_none(self, console: Console):
        console.start_logger()
        await console.stop_logger()
        assert console._log_task is None

    @pytest.mark.asyncio
    async def test_stop_logger_drains_pending_entries_before_returning(
        self, console: Console, stream: io.StringIO
    ):
        console.start_logger()
        console._emit(
            tags=(),
            message="pending",
            payloads={},
            color=Color.RED,
            stream=stream,
            include_time=False,
        )
        await console.stop_logger()

        assert "pending" in stream.getvalue()

    @pytest.mark.asyncio
    async def test_full_round_trip_through_public_log_method(
        self, monkeypatch, console: Console
    ):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.start_logger()
        console.notice("async hello")
        await console.stop_logger()

        assert "async hello" in fake_stdout.getvalue()
        assert console.dropped_log_count == 0


class TestInput:
    def test_returns_stripped_input(self, monkeypatch, console: Console):
        monkeypatch.setattr("builtins.input", lambda prompt: "  hello  ")
        result = console.input("Name:")
        assert result == "hello"

    def test_passes_colored_prompt_to_builtin_input(
        self, monkeypatch, console: Console
    ):
        captured = {}

        def fake_input(prompt):
            captured["prompt"] = prompt
            return "value"

        monkeypatch.setattr("builtins.input", fake_input)
        console.input("Enter name:", color=Color.LIGHT_CYAN, include_time=False)

        assert captured["prompt"] == f"{Color.LIGHT_CYAN}Enter name:{Color.RESET}"

    def test_includes_timestamp_when_requested(
        self, monkeypatch, console: Console, frozen_time: str
    ):
        captured = {}

        def fake_input(prompt):
            captured["prompt"] = prompt
            return "value"

        monkeypatch.setattr("builtins.input", fake_input)
        console.input("Name:", color=Color.RED, include_time=True)

        assert captured["prompt"] == f"{Color.RED}{frozen_time} Name:{Color.RESET}"

    def test_empty_input_strips_to_empty_string(self, monkeypatch, console: Console):
        monkeypatch.setattr("builtins.input", lambda prompt: "   ")
        assert console.input("Name:") == ""


class TestEventDispatch:
    def test_event_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.event(SeverityTag.WARNING, EventTag.JAILED, "user jailed", user="bob")

        spy.assert_called_once_with(
            tags=(SeverityTag.WARNING, EventTag.JAILED),
            message="user jailed",
            payloads={"user": "bob"},
            color=EventTag.JAILED.color,
            stream=sys.stdout,
        )


class TestNoticeDispatch:
    def test_notice_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.notice("all good", foo="bar")

        spy.assert_called_once_with(
            tags=(SeverityTag.NOTICE,),
            message="all good",
            payloads={"foo": "bar"},
            color=SeverityTag.NOTICE.color,
            stream=sys.stdout,
        )

    def test_notice_integration_writes_to_stdout(self, monkeypatch, console: Console):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.notice("all good")

        output = fake_stdout.getvalue()
        assert "[NOTICE]" in output
        assert "all good" in output
        assert output.startswith(str(SeverityTag.NOTICE.color))


class TestWarningDispatch:
    def test_warning_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.warning("careful", code=42)

        spy.assert_called_once_with(
            tags=(SeverityTag.WARNING,),
            message="careful",
            payloads={"code": 42},
            color=SeverityTag.WARNING.color,
            stream=sys.stdout,
        )


class TestCriticalDispatch:
    def test_critical_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.critical("meltdown")

        spy.assert_called_once_with(
            tags=(SeverityTag.CRITICAL,),
            message="meltdown",
            payloads={},
            color=SeverityTag.CRITICAL.color,
            stream=sys.stderr,
        )

    def test_critical_integration_writes_to_stderr(self, monkeypatch, console: Console):
        fake_stderr = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stderr", fake_stderr)

        console.critical("meltdown")

        output = fake_stderr.getvalue()
        assert "[CRITICAL]" in output
        assert "meltdown" in output


class TestErrorDispatch:
    def test_error_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.error("failed", code=500)

        spy.assert_called_once_with(
            tags=(SeverityTag.ERROR,),
            message="failed",
            payloads={"code": 500},
            color=SeverityTag.ERROR.color,
            stream=sys.stderr,
        )

    def test_error_integration_writes_to_stderr(self, monkeypatch, console: Console):
        fake_stderr = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stderr", fake_stderr)

        console.error("failed")

        output = fake_stderr.getvalue()
        assert "[ERROR]" in output
        assert "failed" in output


class TestResponseDispatch:
    def test_response_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.response(3, ResponseTag.SUCCESS, "example.com", status_code=200)

        spy.assert_called_once_with(
            tags=(ResponseTag.SUCCESS,),
            message="example.com",
            payloads={"status_code": 200},
            color=ResponseTag.SUCCESS.color,
            stream=sys.stdout,
            include_none=False,
            log_id=3,
        )

    def test_response_integration_formats_request_id_and_source(
        self, monkeypatch, console: Console
    ):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.response(1, ResponseTag.SUCCESS, "example.com", status_code=200)

        output = fake_stdout.getvalue()
        assert "01" in output
        assert "[SUCCESS]" in output
        assert "example.com" in output
        assert "status_code: 200" in output

    def test_response_excludes_none_payload_values(self, monkeypatch, console: Console):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.response(2, ResponseTag.FAILURE, "sample.com", status_code=None)

        output = fake_stdout.getvalue()
        assert "status_code" not in output


class TestSummaryDispatch:
    def test_summary_calls_emit_with_expected_arguments(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.summary(success=8, failure=2, total_time=12.345)

        spy.assert_called_once_with(
            tags=(SystemTag.SUMMARY,),
            message=(
                "Time: 12.3s | Total: 10 | Success: 8 | Failure: 2 | Success Rate: 80.0%"
            ),
            payloads={"dropped_logs": 0},
            color=SystemTag.SUMMARY.color,
            stream=sys.stdout,
        )

    def test_summary_handles_zero_total_without_dividing_by_zero(
        self, console: Console, monkeypatch
    ):
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.summary(success=0, failure=0, total_time=0.0)

        _, kwargs = spy.call_args
        assert "Success Rate: 0.0%" in kwargs["message"]
        assert "Total: 0" in kwargs["message"]

    def test_summary_includes_current_dropped_log_count(
        self, console: Console, monkeypatch
    ):
        console._dropped_log_count = 4
        spy = MagicMock()
        monkeypatch.setattr(console, "_emit", spy)

        console.summary(success=1, failure=0, total_time=1.0)

        _, kwargs = spy.call_args
        assert kwargs["payloads"] == {"dropped_logs": 4}

    def test_summary_integration_writes_to_stdout(self, monkeypatch, console: Console):
        fake_stdout = io.StringIO()
        monkeypatch.setattr(console_module.sys, "stdout", fake_stdout)

        console.summary(success=3, failure=1, total_time=2.0)

        output = fake_stdout.getvalue()
        assert "[SUMMARY]" in output
        assert "Success Rate: 75.0%" in output
        assert "dropped_logs: 0" in output
