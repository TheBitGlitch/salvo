import asyncio

import pytest

from kernel.core.session_tracker import SessionTracker


class FakeConsole:

    def response(self, *args, **kwargs) -> None:
        pass

    def critical(self, *args, **kwargs) -> None:
        pass


class TestHelpers:

    def test_response_verdict_success(self) -> None:
        assert SessionTracker.response_verdict(200) is True
        assert SessionTracker.response_verdict(201) is True
        assert SessionTracker.response_verdict(204) is True
        assert SessionTracker.response_verdict(205) is True
        assert SessionTracker.response_verdict(207) is True
        assert SessionTracker.response_verdict(209) is True
        assert SessionTracker.response_verdict(301) is True
        assert SessionTracker.response_verdict(302) is True

    def test_response_verdict_failure(self) -> None:
        assert SessionTracker.response_verdict(400) is False
        assert SessionTracker.response_verdict(404) is False
        assert SessionTracker.response_verdict(500) is False

    def test_response_verdict_error_overrides_success(self) -> None:
        assert SessionTracker.response_verdict(200, error="connection error") is False


@pytest.mark.asyncio
class TestSessionTracker:

    async def test_quota_acquire_and_exhaust(self) -> None:
        tracker = SessionTracker(limit=3, fail_tolerance=5, console=FakeConsole())

        assert await tracker.acquire_slot() is True
        assert await tracker.acquire_slot() is True
        assert await tracker.acquire_slot() is True
        assert await tracker.acquire_slot() is False

    async def test_release_refund_increases_credit(self) -> None:
        tracker = SessionTracker(limit=1, fail_tolerance=5, console=FakeConsole())

        assert await tracker.acquire_slot() is True
        assert tracker.exhausted is True

        await tracker.release_slot(True)

        assert tracker.exhausted is False
        assert await tracker.acquire_slot() is True

    async def test_limit_stops_execution(self) -> None:
        tracker = SessionTracker(limit=1, fail_tolerance=5, console=FakeConsole())

        assert await tracker.report(source="api", status_code=200) is False

        assert tracker.is_stopped is True

    async def test_success_resets_consecutive_failures(self) -> None:
        tracker = SessionTracker(limit=None, fail_tolerance=10, console=FakeConsole())

        await tracker.report("api", 500)
        await tracker.report("api", 500)

        assert tracker._consec_fail == 2

        await tracker.report("api", 200)

        assert tracker._consec_fail == 0

    async def test_acquire_fails_when_stopped(self) -> None:
        tracker = SessionTracker(limit=None, fail_tolerance=10, console=FakeConsole())

        tracker.stop_event.set()

        assert await tracker.acquire_slot() is False

    async def test_fail_tolerance_stops(self) -> None:
        tracker = SessionTracker(limit=None, fail_tolerance=2, console=FakeConsole())

        assert await tracker.report(source="api", status_code=500) is True

        assert await tracker.report(source="api", status_code=500) is False

        assert tracker.is_stopped is True

    async def test_reset_consecutive_failures(self) -> None:
        tracker = SessionTracker(limit=None, fail_tolerance=10, console=FakeConsole())

        await tracker.report("api", 500)
        await tracker.report("api", 500)

        assert tracker._consec_fail == 2

        await tracker.reset_consec_fail()

        assert tracker._consec_fail == 0

    async def test_clear_stop_event(self) -> None:
        tracker = SessionTracker(limit=1, fail_tolerance=10, console=FakeConsole())

        await tracker.report("api", 200)

        assert tracker.is_stopped is True

        await tracker.clear_stop_event()

        assert tracker.is_stopped is False

    async def test_concurrent_acquire_respects_limit(self) -> None:
        tracker = SessionTracker(limit=50, fail_tolerance=10, console=FakeConsole())

        results = await asyncio.gather(*[tracker.acquire_slot() for _ in range(200)])

        assert sum(results) == 50
