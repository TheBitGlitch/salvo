from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiohttp import ClientSession, TCPConnector
from fake_useragent import UserAgent

from .api_pool import ApiPool
from .session_tracker import SessionTracker

from kernel.api.models import ApiSlot, ApiCall
from kernel.libs.printer import Console
from kernel.libs.printer.tags import SeverityTag, EventTag, ResponseTag

if TYPE_CHECKING:
    from cli.sub_apps import RuntimeArgs


class Engine:
    """Coordinates concurrent API execution and runtime session control."""

    @staticmethod
    async def _send_request(
        session: ClientSession,
        api_call: ApiCall,
        timeout: int,
        headers: dict[str, str],
        proxy: str | None = None,
    ) -> int:
        """
        Sends an API request using the given API call.

        Args:
            session: Shared HTTP session used to send the request.
            api_call: API request definition to execute.
            timeout: Maximum request duration in seconds.
            headers: HTTP headers to include with the request.
            proxy: Optional proxy used for the request.

        Returns:
            The HTTP status code, or `0` if the method is unsupported.
        """
        match api_call.method:
            case "POST":
                async with session.post(
                    url=api_call.url,
                    json=api_call.json,
                    data=api_call.data,
                    headers=headers,
                    timeout=timeout,
                    proxy=proxy,
                ) as response:
                    status_code = response.status

            case "GET":
                async with session.get(
                    url=api_call.url, headers=headers, timeout=timeout, proxy=proxy
                ) as response:
                    status_code = response.status

            case _:
                status_code = 0

        return status_code

    @staticmethod
    def _current_time() -> float:
        """Returns the current monotonic event-loop time."""
        return asyncio.get_running_loop().time()

    def __init__(
        self,
        api_slots: tuple[ApiSlot, ...],
        runtime_args: RuntimeArgs,
        console: Console,
    ) -> None:
        """
        Initializes the execution engine.

        Args:
            api_slots: Validated API slots from the API factory, used by the API pool.
            runtime_args: Validated runtime configuration.
            console: Console instance used for logging and status reporting.
        """
        self._api_pool = ApiPool(
            api_slots=api_slots, bounded=runtime_args.bounded, console=console
        )
        self._tracker = SessionTracker(
            limit=runtime_args.limit,
            fail_tolerance=runtime_args.fail_tolerance,
            console=console,
        )
        self._console = console

        self._runtime_args = runtime_args
        # Runtime state kept separate from the immutable configuration.
        self._runtime_proxy = runtime_args.proxy

        self._fallback_lock = asyncio.Lock()

        self._user_agent = UserAgent()
        self._request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _dispatch_request(
        self, session: ClientSession, api_call: ApiCall, user_agent: str
    ) -> tuple[bool, bool | None]:
        """
        Executes one API request and reports its result to the session tracker.

        Acquires an execution slot, sends the request, evaluates its response,
        and updates the session state.

        Args:
            session: Shared HTTP session used to send the request.
            api_call: API request definition to execute.
            user_agent: User-Agent value to use for the request.

        Returns:
            A tuple of `(should_continue, verdict)`. A `None` verdict indicates
            that the request was ignored, such as when its API was jailed.
        """
        if not await self._tracker.acquire_slot():
            return False, None

        try:
            status_code = await self._send_request(
                session=session,
                api_call=api_call,
                timeout=self._runtime_args.timeout,
                headers={**self._request_headers, "User-Agent": user_agent},
                proxy=self._runtime_proxy,
            )

        except Exception as exc:
            await self._tracker.release_slot(refund=True)

            if self._api_pool.is_jailed(api_call.source):
                return True, None

            should_continue = await self._tracker.report(
                source=api_call.source,
                status_code=0,
                error=type(exc).__name__,
            )

            return should_continue, False

        verdict = self._tracker.response_verdict(status_code)

        if self._api_pool.is_jailed(api_call.source):
            await self._tracker.release_slot(refund=True)

            self._console.response(
                request_id=0,
                tag=ResponseTag.ZOMBIE,
                source=api_call.source,
                status_code=status_code,
            )

            return True, None

        await self._tracker.release_slot(refund=(not verdict))

        should_continue = await self._tracker.report(
            source=api_call.source, status_code=status_code
        )

        return should_continue, verdict

    async def _worker(
        self, worker_id: int, session: ClientSession, user_agent: str
    ) -> None:
        """
        Runs a worker loop that continuously executes available API calls.

        The worker maintains API routing context and handles proxy fallback
        when the configured consecutive-failure threshold is reached.

        Args:
            worker_id: Identifier used for worker status messages.
            session: Shared HTTP session used by the worker.
            user_agent: User-Agent value used by the worker.
        """
        previous_source = None
        previous_verdict = None

        while not self._tracker.is_stopped:

            api_call = await self._api_pool.next_call(
                previous_source=previous_source,
                previous_verdict=previous_verdict,
            )

            if api_call is None:
                self._console.notice(
                    f"Worker {worker_id:02d}; API pool is fully depleted."
                )
                return

            should_continue, verdict = await self._dispatch_request(
                session=session,
                api_call=api_call,
                user_agent=user_agent,
            )

            if verdict is None:
                previous_source = None
                previous_verdict = None
                continue

            previous_source = api_call.source
            previous_verdict = verdict

            async with self._fallback_lock:
                if (
                    self._runtime_proxy
                    and self._runtime_args.fallback
                    and self._runtime_args.bounded
                    and self._tracker.consec_fail >= self._tracker.fail_tolerance
                ):
                    self._console.event(
                        severity=SeverityTag.NOTICE,
                        event=EventTag.FALLBACK,
                        message=(
                            f"Proxy {self._runtime_proxy} failed "
                            f"{self._tracker.consec_fail} times. "
                            "Falling back to direct connection."
                        ),
                    )

                    self._runtime_proxy = None

                    await self._tracker.reset_consec_fail()
                    await self._tracker.clear_stop_event()

                    should_continue = True

            if not should_continue:
                break

        self._console.notice(
            f"Worker {worker_id:02d} shutting down; mission terminated."
        )

    async def _execute(self) -> None:
        """
        Runs the asynchronous execution lifecycle.

        Creates the HTTP session, starts the configured workers, waits for
        their completion, and reports final execution statistics.
        """
        self._console.start_logger()
        start_time = self._current_time()

        tcp_connector = TCPConnector(
            ssl=self._runtime_args.ssl,
            limit=self._runtime_args.concurrency,
        )

        async with ClientSession(connector=tcp_connector) as session:
            try:
                workers = [
                    asyncio.create_task(
                        self._worker(i, session, self._user_agent.random)
                    )
                    for i in range(1, self._runtime_args.concurrency + 1)
                ]

                self._console.notice(
                    f"All {self._runtime_args.concurrency} workers are running."
                )

                await asyncio.gather(*workers)

            except asyncio.CancelledError:
                self._console.warning("Mission aborted by operator.")

            finally:
                self._tracker.stop_event.set()
                elapsed_time = self._current_time() - start_time

                self._console.notice("Mission completed.")
                self._console.summary(
                    success=self._tracker.success,
                    failure=self._tracker.failure,
                    total_time=elapsed_time,
                )

                await self._console.stop_logger()

    def launch(self) -> None:
        """Starts the engine and runs its asynchronous execution lifecycle."""

        self._console.notice(message="Mission started.", **self._runtime_args.asdict)
        asyncio.run(self._execute())
