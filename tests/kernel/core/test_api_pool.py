import asyncio
from unittest.mock import MagicMock, patch

import pytest

from kernel.api.models import ApiCall, ApiSlot
from kernel.core.api_pool import ApiPool
from kernel.libs.printer.tags import EventTag, SeverityTag


def make_api_call(source: str) -> ApiCall:
    return ApiCall(source=source, url=f"https://example.test/{source}", method="GET")


def make_api_slot(
    index: int,
    capacity: int = 5,
    ticket: int = 100,
    source: str | None = None,
    strikes: int = 0,
    was_jailed: bool = False,
    jailed_until: float | None = None,
) -> ApiSlot:
    return ApiSlot(
        index=index,
        call=make_api_call(source or f"api-{index}"),
        capacity=capacity,
        ticket=ticket,
        strikes=strikes,
        was_jailed=was_jailed,
        jailed_until=jailed_until,
    )


@pytest.fixture
def console() -> MagicMock:
    return MagicMock()


@pytest.fixture
def make_slots():
    """Factory fixture: builds a tuple of real ``ApiSlot`` objects from
    ``(index, capacity, ticket)`` triples, e.g.
    ``make_slots([(1, 5, 1.0), (2, 3, 2.0)])``."""

    def _make(specs):
        return tuple(
            make_api_slot(index=spec[0], capacity=spec[1], ticket=spec[2])
            for spec in specs
        )

    return _make


def make_pool(slots, bounded: bool, console: MagicMock) -> ApiPool:
    return ApiPool(api_slots=slots, bounded=bounded, console=console)


class TestInitialization:
    def test_bounded_weights_are_capacity_times_ticket(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0), (2, 3, 2.0), (3, 10, 0.5)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool._get_weight(slots[0]) == 5.0
        assert pool._get_weight(slots[1]) == 6.0
        assert pool._get_weight(slots[2]) == 5.0

    def test_unbounded_weights_are_all_equal(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0), (2, 3, 2.0), (3, 10, 0.5)])
        pool = make_pool(slots, bounded=False, console=console)

        assert pool._get_weight(slots[0]) == 1.0
        assert pool._get_weight(slots[1]) == 1.0
        assert pool._get_weight(slots[2]) == 1.0

    def test_bounded_strike_limit_and_jail_duration(self, make_slots, console):
        pool = make_pool(make_slots([(1, 5, 1.0)]), bounded=True, console=console)

        assert pool.strike_limit == 3
        assert pool.jail_duration == 20.0

    def test_unbounded_strike_limit_and_jail_duration_are_zero(
        self, make_slots, console
    ):
        pool = make_pool(make_slots([(1, 5, 1.0)]), bounded=False, console=console)

        assert pool.strike_limit == 0
        assert pool.jail_duration == 0.0

    def test_slots_are_sorted_by_index_regardless_of_input_order(
        self, make_slots, console
    ):
        slots = make_slots([(3, 1, 1.0), (1, 1, 1.0), (2, 1, 1.0)])
        pool = make_pool(slots, bounded=False, console=console)

        assert [slot.index for slot in pool._slots] == [1, 2, 3]

    def test_source_to_index_mapping_is_built_from_slots(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0), (2, 3, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool._source_to_index == {
            slots[0].call.source: 1,
            slots[1].call.source: 2,
        }

    def test_removed_indices_starts_empty(self, make_slots, console):
        pool = make_pool(make_slots([(1, 5, 1.0)]), bounded=True, console=console)

        assert pool._removed_indices == set()

    def test_lock_is_an_asyncio_lock(self, make_slots, console):
        pool = make_pool(make_slots([(1, 5, 1.0)]), bounded=True, console=console)

        assert isinstance(pool._lock, asyncio.Lock)


class TestWeightHelpers:
    def test_get_weight_returns_current_slot_weight(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0), (2, 3, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool._get_weight(slots[0]) == 5.0
        assert pool._get_weight(slots[1]) == 6.0

    def test_set_weight_updates_underlying_tree_when_delta_nonzero(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        pool._set_weight(slots[0], 2.5)

        assert pool._get_weight(slots[0]) == 2.5

    def test_set_weight_is_a_noop_when_delta_is_zero(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._pool.update = MagicMock(wraps=pool._pool.update)

        pool._set_weight(slots[0], 5.0)

        pool._pool.update.assert_not_called()


class TestGetSlot:
    def test_get_slot_returns_slot_matching_one_based_index(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0), (2, 3, 2.0), (3, 1, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool._get_slot(1) is slots[0]
        assert pool._get_slot(2) is slots[1]
        assert pool._get_slot(3) is slots[2]


class TestSelectCall:
    def test_returns_none_when_total_weight_is_zero(self, make_slots, console):
        slots = make_slots([(1, 0, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool._select_call() is None

    def test_returns_none_when_query_finds_no_index(self, make_slots, console):
        # Defensive branch: the real FenwickTree only returns None when its
        # total is non-positive (already guarded above), so this exercises
        # ApiPool's own None-handling by stubbing query() directly.
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._pool.query = MagicMock(return_value=None)

        with patch("random.random", return_value=0.5):
            assert pool._select_call() is None

    def test_unbounded_returns_call_and_does_not_touch_capacity(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=False, console=console)

        with patch("random.random", return_value=0.0):
            result = pool._select_call()

        assert result is slots[0].call
        assert slots[0].capacity == 5
        assert pool._get_weight(slots[0]) == 1.0

    def test_bounded_consumes_one_unit_of_capacity_and_reweights(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)

        # target <= 0 always resolves to index 1 in the real FenwickTree.
        with patch("random.random", return_value=0.0):
            result = pool._select_call()

        assert result is slots[0].call
        assert slots[0].capacity == 4
        # new weight = capacity(4) * ticket(2.0) = 8.0
        assert pool._get_weight(slots[0]) == 8.0
        assert pool._removed_indices == set()

    def test_bounded_removes_slot_once_capacity_is_exhausted(
        self, make_slots, console
    ):
        slots = make_slots([(1, 1, 3.0)])
        pool = make_pool(slots, bounded=True, console=console)

        with patch("random.random", return_value=0.0):
            result = pool._select_call()

        assert result is slots[0].call
        assert slots[0].capacity == 0
        assert pool._get_weight(slots[0]) == 0.0
        assert pool._removed_indices == {1}

    def test_selection_target_is_scaled_by_total_weight(self, make_slots, console):
        # Two slots, weights [3.0, 7.0], total = 10.0.
        # random.random() == 0.5 -> target == 5.0, which (per the real
        # FenwickTree's lower-bound walk) resolves to slot 2.
        slots = make_slots([(1, 3, 1.0), (2, 7, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        with patch("random.random", return_value=0.5):
            result = pool._select_call()

        assert result is slots[1].call

    def test_selection_near_total_favors_last_slot(self, make_slots, console):
        # Weights [3.0, 7.0], total = 10.0. random.random() close to 1.0
        # pushes target close to (but under) total, which still resolves
        # to slot 2, and a target that overshoots total clamps to the
        # last index as well.
        slots = make_slots([(1, 3, 1.0), (2, 7, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        with patch("random.random", return_value=0.999):
            result = pool._select_call()

        assert result is slots[1].call


class TestHandleSuccess:
    def test_resets_strikes_and_jail_flags(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].strikes = 2
        slots[0].was_jailed = True
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_success(slots[0].call.source)

        assert slots[0].strikes == 0
        assert slots[0].was_jailed is False
        assert slots[0].jailed_until is None

    def test_unknown_source_is_ignored(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].strikes = 2
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_success("does-not-exist")

        assert slots[0].strikes == 2

    def test_currently_jailed_slot_is_left_untouched(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].jailed_until = 1234.0
        slots[0].strikes = 2
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_success(slots[0].call.source)

        assert slots[0].strikes == 2
        assert slots[0].jailed_until == 1234.0


class TestHandleFailure:
    def test_increments_strikes_below_limit(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_failure(slots[0].call.source)

        assert slots[0].strikes == 1
        console.event.assert_not_called()

    def test_unknown_source_is_ignored(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_failure("does-not-exist")

        assert slots[0].strikes == 0

    def test_removed_index_is_ignored(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._removed_indices.add(1)

        pool._handle_failure(slots[0].call.source)

        assert slots[0].strikes == 0

    def test_already_jailed_slot_is_ignored(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].jailed_until = 999.0
        pool = make_pool(slots, bounded=True, console=console)

        pool._handle_failure(slots[0].call.source)

        assert slots[0].strikes == 0

    def test_jails_slot_after_reaching_strike_limit(self, make_slots, console):
        slots = make_slots([(1, 5, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)
        slots[0].strikes = pool.strike_limit - 1

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._handle_failure(slots[0].call.source)

        assert slots[0].was_jailed is True
        assert slots[0].strikes == 0
        assert slots[0].jailed_until == 100.0 + pool.jail_duration
        assert pool._get_weight(slots[0]) == 0.0
        console.event.assert_called_once_with(
            SeverityTag.NOTICE,
            EventTag.JAILED,
            message=f"API `{slots[0].call.source}` jailed for {pool.jail_duration}s.",
        )

    def test_permanently_removes_slot_after_second_jail(self, make_slots, console):
        slots = make_slots([(1, 5, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)
        slots[0].was_jailed = True
        slots[0].strikes = pool.strike_limit - 1

        pool._handle_failure(slots[0].call.source)

        assert pool._removed_indices == {1}
        assert pool._get_weight(slots[0]) == 0.0
        console.event.assert_called_once_with(
            SeverityTag.NOTICE,
            EventTag.PURGED,
            message=f"API `{slots[0].call.source}` permanently removed after second jail.",
        )


class TestReleaseExpiredJails:
    def test_frees_slot_whose_jail_has_expired_and_has_capacity(
        self, make_slots, console
    ):
        slots = make_slots([(1, 4, 2.0)])
        slots[0].jailed_until = 50.0
        pool = make_pool(slots, bounded=True, console=console)
        pool._set_weight(slots[0], 0.0)  # mimic the zeroed weight of a jailed slot

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._release_expired_jails()

        assert slots[0].jailed_until is None
        assert pool._get_weight(slots[0]) == 8.0
        console.event.assert_called_once_with(
            SeverityTag.NOTICE,
            EventTag.FREED,
            message=f"API `{slots[0].call.source}` freed from jail.",
        )

    def test_does_not_free_jail_that_has_not_expired_yet(self, make_slots, console):
        slots = make_slots([(1, 4, 2.0)])
        slots[0].jailed_until = 500.0
        pool = make_pool(slots, bounded=True, console=console)
        pool._set_weight(slots[0], 0.0)

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._release_expired_jails()

        assert slots[0].jailed_until == 500.0
        assert pool._get_weight(slots[0]) == 0.0
        console.event.assert_not_called()

    def test_skips_slots_that_have_been_permanently_removed(
        self, make_slots, console
    ):
        slots = make_slots([(1, 4, 2.0)])
        slots[0].jailed_until = 50.0
        pool = make_pool(slots, bounded=True, console=console)
        pool._set_weight(slots[0], 0.0)
        pool._removed_indices.add(1)

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._release_expired_jails()

        assert slots[0].jailed_until == 50.0
        assert pool._get_weight(slots[0]) == 0.0
        console.event.assert_not_called()

    def test_clears_jailed_until_without_reweighting_when_capacity_is_zero(
        self, make_slots, console
    ):
        slots = make_slots([(1, 0, 2.0)])
        slots[0].jailed_until = 50.0
        pool = make_pool(slots, bounded=True, console=console)

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._release_expired_jails()

        assert slots[0].jailed_until is None
        assert pool._get_weight(slots[0]) == 0.0
        console.event.assert_not_called()

    def test_ignores_slots_that_are_not_jailed(self, make_slots, console):
        slots = make_slots([(1, 4, 2.0)])
        pool = make_pool(slots, bounded=True, console=console)

        with patch.object(ApiPool, "_current_time", return_value=100.0):
            pool._release_expired_jails()

        assert slots[0].jailed_until is None
        console.event.assert_not_called()


class TestProcessVerdict:
    def test_true_verdict_delegates_to_handle_success(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._handle_success = MagicMock()
        pool._handle_failure = MagicMock()

        pool._process_verdict(slots[0].call.source, True)

        pool._handle_success.assert_called_once_with(slots[0].call.source)
        pool._handle_failure.assert_not_called()

    def test_false_verdict_delegates_to_handle_failure(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._handle_success = MagicMock()
        pool._handle_failure = MagicMock()

        pool._process_verdict(slots[0].call.source, False)

        pool._handle_failure.assert_called_once_with(slots[0].call.source)
        pool._handle_success.assert_not_called()


class TestIsJailed:
    def test_always_false_when_unbounded(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].jailed_until = 999.0
        pool = make_pool(slots, bounded=False, console=console)

        assert pool.is_jailed(slots[0].call.source) is False

    def test_true_for_a_currently_jailed_slot(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        slots[0].jailed_until = 999.0
        pool = make_pool(slots, bounded=True, console=console)

        assert pool.is_jailed(slots[0].call.source) is True

    def test_false_for_a_non_jailed_slot(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool.is_jailed(slots[0].call.source) is False

    def test_false_for_an_unknown_source(self, make_slots, console):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        assert pool.is_jailed("does-not-exist") is False


class TestNextCall:
    @pytest.mark.asyncio
    async def test_unbounded_selects_directly_without_processing_verdict(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=False, console=console)
        pool._process_verdict = MagicMock()
        pool._release_expired_jails = MagicMock()

        with patch("random.random", return_value=0.0):
            result = await pool.next_call(
                previous_source=slots[0].call.source, previous_verdict=True
            )

        assert result is slots[0].call
        pool._process_verdict.assert_not_called()
        pool._release_expired_jails.assert_not_called()

    @pytest.mark.asyncio
    async def test_bounded_processes_verdict_then_releases_jails_then_selects(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        call_order = []
        pool._process_verdict = MagicMock(
            side_effect=lambda *a, **kw: call_order.append("process_verdict")
        )
        pool._release_expired_jails = MagicMock(
            side_effect=lambda: call_order.append("release_expired_jails")
        )
        pool._select_call = MagicMock(
            side_effect=lambda: call_order.append("select_call") or slots[0].call
        )

        result = await pool.next_call(
            previous_source=slots[0].call.source, previous_verdict=False
        )

        assert result is slots[0].call
        assert call_order == [
            "process_verdict",
            "release_expired_jails",
            "select_call",
        ]
        pool._process_verdict.assert_called_once_with(slots[0].call.source, False)

    @pytest.mark.asyncio
    async def test_bounded_skips_process_verdict_when_no_previous_result(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._process_verdict = MagicMock()
        pool._release_expired_jails = MagicMock()

        with patch("random.random", return_value=0.0):
            await pool.next_call()

        pool._process_verdict.assert_not_called()
        pool._release_expired_jails.assert_called_once()

    @pytest.mark.asyncio
    async def test_bounded_skips_process_verdict_when_only_source_given(
        self, make_slots, console
    ):
        slots = make_slots([(1, 5, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)
        pool._process_verdict = MagicMock()

        with patch("random.random", return_value=0.0):
            await pool.next_call(previous_source=slots[0].call.source)

        pool._process_verdict.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_selectable_api_remains(
        self, make_slots, console
    ):
        slots = make_slots([(1, 0, 1.0)])
        pool = make_pool(slots, bounded=True, console=console)

        result = await pool.next_call()

        assert result is None
