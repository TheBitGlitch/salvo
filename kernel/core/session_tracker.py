import asyncio

from kernel.libs.printer import Console
from kernel.libs.printer.tags import ResponseTag


class SessionTracker:
    """
    Tracks session execution state, statistics, and stop conditions.

    Manages execution credits to prevent successful-request overshoot,
    monitors consecutive failures, and signals when the session should stop.
    """

    @staticmethod
    def response_verdict(status_code: int, error: str | None = None) -> bool:
        """
        Determines whether a completed request is considered successful.

        Treats 2xx, 301 and 302 HTTP status codes as successful.

        Args:
            status_code: HTTP status code returned by the request.
            error: Error message associated with the request, if any.

        Returns:
            `True` if the request is considered successful, `False` otherwise.
        """
        if error:
            return False

        return (199 < status_code < 300) or status_code in (301, 302)

    def __init__(
        self, limit: int | None, fail_tolerance: int, console: Console
    ) -> None:
        """
        Initialize the session tracker.

        Args:
            limit: Maximum number of successful requests before stopping
                the session. `None` disables the limit.
            fail_tolerance: Maximum number of consecutive failures before
                stopping the session.
            console: Console instance used for reporting events and progress.
        """
        self._id = 0
        self._active_slots = 0
        self._success = 0
        self._failure = 0
        self._consec_fail = 0

        self._limit = limit
        self._fail_tolerance = fail_tolerance
        self._credits = limit

        self._console = console
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    @property
    def success(self) -> int:
        return self._success

    @property
    def failure(self) -> int:
        return self._failure

    @property
    def consec_fail(self) -> int:
        return self._consec_fail

    @property
    def fail_tolerance(self) -> int | None:
        return self._fail_tolerance

    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def stop_event(self) -> asyncio.Event:
        return self._stop_event

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    @property
    def exhausted(self) -> bool:
        return self._credits is not None and self._credits <= 0

    async def acquire_slot(self) -> bool:
        """
        Attempt to reserve an execution slot.

        Returns:
            `True` if a slot was reserved successfully, `False` if the
            session has stopped or the available execution credits are
            exhausted.
        """
        async with self._lock:
            if self.is_stopped:
                return False

            if self.exhausted:
                return False

            if self._credits is not None:
                self._credits -= 1

            self._active_slots += 1
            return True

    async def release_slot(self, refund: bool) -> None:
        """
        Release a previously reserved execution slot.

        Args:
            refund: Whether to restore the execution credit consumed
                by the released slot.
        """
        async with self._lock:
            # Defensive guard: release_slot() is expected to be paired with
            # a successful acquire_slot(). Clamp to zero to avoid destabilizing
            # the mission in case of an unexpected mismatch.
            self._active_slots = max(0, self._active_slots - 1)

            if refund and self._credits is not None:
                self._credits += 1

    async def report(
        self, source: str, status_code: int, error: str | None = None
    ) -> bool:
        """
        Record the outcome of a completed request.

        Updates execution statistics, reports the result through the console,
        and evaluates session stop conditions.

        Args:
            source: Identifier of the API source.
            status_code: HTTP status code returned by the request.
            error: Error message associated with the request, if any.

        Returns:
            `True` if the session should continue, `False` if a stop condition
            has been met.
        """
        async with self._lock:
            verdict = self.response_verdict(status_code, error)

            self._id += 1
            request_id = self._id

            if verdict:
                self._success += 1
                self._consec_fail = 0
                resp_tag = ResponseTag.SUCCESS

            else:
                self._failure += 1
                self._consec_fail += 1
                resp_tag = ResponseTag.FAILURE

            self._console.response(
                request_id=request_id,
                tag=resp_tag,
                source=source,
                code=status_code,
                error=error if error else None,
            )

            if self._limit is not None and self._success >= self._limit:
                self._stop_event.set()
                return False

            if self._fail_tolerance and self._consec_fail >= self._fail_tolerance:

                self._console.critical(
                    f"Consecutive failure tolerance reached ({self._fail_tolerance}). "
                    "Connection reliability has been compromised."
                )

                self._stop_event.set()
                return False

            if self.is_stopped:
                return False

            return True

    async def reset_consec_fail(self) -> None:
        """
        Reset the consecutive failure counter.

        Intended for recovery scenarios where previous failures should no
        longer contribute toward the configured tolerance threshold.
        """
        async with self._lock:
            self._consec_fail = 0

    async def clear_stop_event(self) -> None:
        """
        Clear the session stop signal.

        Intended for controlled recovery scenarios where execution is allowed
        to resume after being stopped.
        """
        async with self._lock:
            self._stop_event.clear()
