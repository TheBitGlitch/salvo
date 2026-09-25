import random
import asyncio

from kernel.api.models import ApiCall, ApiSlot
from kernel.libs.printer import Console
from kernel.libs.printer.tags import SeverityTag, EventTag
from kernel.libs.structures import FenwickTree


class ApiPool:
    """
    Manages API selection and runtime API lifecycle state.

    ApiPool selects ApiCalls from a collection of ApiSlots using weighted
    random sampling backed by a Fenwick Tree. In bounded mode, API capacity
    and failure state dynamically control each slot's selection weight.

    The pool supports two execution modes:

        - Bounded mode:
            - APIs are monitored based on capacity and request failures.
            - Capacity is consumed after each selection.
            - Failed APIs can be temporarily jailed or permanently removed.

        - Unbounded mode:
            - APIs are not monitored.
            - APIs remain continuously available.
            - Selection uses equal weights.
    """

    @staticmethod
    def _current_time() -> float:
        """Returns the current monotonic event-loop time."""
        return asyncio.get_running_loop().time()

    def __init__(
        self, api_slots: tuple[ApiSlot, ...], bounded: bool, console: Console
    ) -> None:
        """
        Args:
            api_slots: API slots validated and indexed by the factory, available for selection.
            bounded: Whether to enable runtime monitoring and lifecycle management
                based on API capacity and request failures.
            console: Console instance used to report API lifecycle events.

        Internal state:
            _slots: Ordered collection of API slots using one-based indices.
            _pool: Fenwick Tree containing the current selection weights.
            _source_to_index: Mapping from API source to its slot index.
            _removed_indices: Indices of APIs permanently removed from the pool.
            _lock: `asyncio` lock protecting bounded-mode state transitions.
            _strike_limit: The number of consecutive failures required to trigger a jail.
            _jail_duration: The duration of a temporary API jail in seconds.
        """

        self._slots: list[ApiSlot] = sorted(api_slots, key=lambda slot: slot.index)

        self._bounded = bounded
        self._console = console

        self._source_to_index: dict[str, int] = {
            slot.call.source: slot.index for slot in self._slots
        }

        if bounded:
            self._pool = FenwickTree(
                [float(slot.capacity * slot.ticket) for slot in self._slots]
            )

            self._strike_limit = 3
            self._jail_duration = 20.0

        else:
            self._pool = FenwickTree([1.0 for _ in self._slots])

            self._strike_limit = 0
            self._jail_duration = 0.0

        self._lock = asyncio.Lock()
        self._removed_indices: set[int] = set()

    @property
    def strike_limit(self) -> int:
        """Returns the number of consecutive failures required to trigger a jail."""
        return self._strike_limit

    @property
    def jail_duration(self) -> float:
        """Returns the duration of a temporary API jail in seconds."""
        return self._jail_duration

    def _get_weight(self, slot: ApiSlot) -> float:
        """
        Returns the current selection weight of an API slot.

        The weight is obtained from the difference between two Fenwick Tree
        prefix sums.
        """
        return self._pool.prefix_sum(slot.index) - self._pool.prefix_sum(slot.index - 1)

    def _set_weight(self, slot: ApiSlot, new_weight: float) -> None:
        """
        Updates an API slot's selection weight.

        Args:
            slot: API slot whose weight is being updated.
            new_weight: New absolute selection weight.
        """
        delta = new_weight - self._get_weight(slot)

        if delta != 0:
            self._pool.update(slot.index, delta)

    def _get_slot(self, index: int) -> ApiSlot:
        """
        Returns the API slot at a one-based index.

        Args:
            index: one-based slot index.

        Returns:
            The API slot at the specified index.
        """
        return self._slots[index - 1]

    def _select_call(self) -> ApiCall | None:
        """
        Selects an API call using weighted random sampling.

        In bounded mode, selecting a call also consumes one unit of the
        selected API's capacity and updates its selection weight.

        Returns:
            The selected API call, or `None` if no selectable API remains.
        """
        total = self._pool.total()

        if total <= 0:
            return None

        target = random.random() * total
        index = self._pool.query(target)

        if index is None:
            return None

        slot = self._get_slot(index)

        if not self._bounded:
            return slot.call

        slot.capacity -= 1

        if slot.capacity <= 0:
            self._set_weight(slot, 0.0)
            self._removed_indices.add(index)

        else:
            self._set_weight(slot, float(slot.capacity * slot.ticket))

        return slot.call

    def _handle_success(self, source: str) -> None:
        """
        Clears the failure state of an API after a successful request.

        Args:
            source: API source identifier.
        """
        index = self._source_to_index.get(source)

        if index is None:
            return

        slot = self._get_slot(index)

        if slot.jailed_until is not None:
            return

        slot.strikes = 0
        slot.was_jailed = False
        slot.jailed_until = None

    def _handle_failure(self, source: str) -> None:
        """
        Registers a failed API request and applies failure-based state changes.

        An API is temporarily jailed after reaching the strike limit and
        permanently removed if it reaches the strike limit again after being
        released from a previous jail.

        Args:
            source: API source identifier.
        """
        index = self._source_to_index.get(source)

        if index is None:
            return

        slot = self._get_slot(index)

        if index in self._removed_indices:
            return

        if slot.jailed_until is not None:
            return

        slot.strikes += 1

        if slot.strikes < self._strike_limit:
            return

        if slot.was_jailed:
            self._set_weight(slot, 0.0)
            self._removed_indices.add(index)

            self._console.event(
                SeverityTag.NOTICE,
                EventTag.PURGED,
                message=f"API `{source}` permanently removed after second jail.",
            )

        else:
            self._set_weight(slot, 0.0)

            slot.jailed_until = self._current_time() + self._jail_duration
            slot.strikes = 0
            slot.was_jailed = True

            self._console.event(
                SeverityTag.NOTICE,
                EventTag.JAILED,
                message=f"API `{source}` jailed for {self._jail_duration}s.",
            )

    def _release_expired_jails(self) -> None:
        """
        Restores APIs whose temporary jail period has expired.

        APIs that still have available capacity are returned to the
        selection pool with their current capacity-based weight.
        """
        now = self._current_time()

        for slot in self._slots:
            if slot.index in self._removed_indices:
                continue

            if slot.jailed_until is not None and now >= slot.jailed_until:
                slot.jailed_until = None

                if slot.capacity > 0:
                    self._set_weight(slot, float(slot.capacity * slot.ticket))

                    self._console.event(
                        SeverityTag.NOTICE,
                        EventTag.FREED,
                        message=f"API `{slot.call.source}` freed from jail.",
                    )

    def _process_verdict(self, source: str, verdict: bool) -> None:
        """
        Applies the result of a previous API request.

        Args:
            source: API source identifier.
            verdict: Whether the previous API request succeeded.
        """
        if verdict:
            self._handle_success(source)

        else:
            self._handle_failure(source)

    def is_jailed(self, source: str) -> bool:
        """
        Checks whether an API is currently jailed.

        Args:
            source: API source identifier.

        Returns:
            `True` if the API is currently jailed, otherwise `False`.
        """
        if not self._bounded:
            return False

        index = self._source_to_index.get(source)

        if index is None:
            return False

        return self._get_slot(index).jailed_until is not None

    async def next_call(
        self,
        previous_source: str | None = None,
        previous_verdict: bool | None = None,
    ) -> ApiCall | None:
        """
        Processes the previous API result and selects the next API call.

        In bounded mode, the previous verdict is applied, expired jails are
        released, and the next call is selected while holding the pool lock.

        Args:
            previous_source: Source of the previously executed API.
            previous_verdict: Result of the previous API request.

        Returns:
            The next API call, or `None` if no selectable API remains.
        """
        if not self._bounded:
            return self._select_call()

        async with self._lock:
            if previous_source is not None and previous_verdict is not None:
                self._process_verdict(previous_source, previous_verdict)

            self._release_expired_jails()

            return self._select_call()
