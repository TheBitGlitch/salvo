import time
import random
import itertools

import pytest

from kernel.libs.structures import FenwickTree


def naive_prefix(array: list[float], index: int) -> float:
    return sum(array[:index])


def naive_query(array: list[float], target: float) -> int | None:
    total = sum(array)

    if total <= 0:
        return None

    if target <= 0:
        return 1

    acc = 0.0
    for i, v in enumerate(array, start=1):
        acc += v

        if acc >= target:
            return i

    return len(array)


class TestConstruction:

    def test_empty(self) -> None:
        fwt = FenwickTree([])

        assert fwt.size == 0
        assert fwt.total() == 0.0

    def test_single_element(self) -> None:
        fwt = FenwickTree([7.0])

        assert fwt.size == 1
        assert fwt.total() == 7.0
        assert fwt.prefix_sum(1) == 7.0

    def test_all_zeros(self) -> None:
        fwt = FenwickTree([0.0] * 5)

        assert fwt.total() == 0.0

        for i in range(1, 6):
            assert fwt.prefix_sum(i) == 0.0

    def test_sparse_array(self) -> None:
        array = [0.0, 0.0, 3.0, 0.0, 0.0]
        fwt = FenwickTree(array)

        assert fwt.prefix_sum(2) == 0.0
        assert fwt.prefix_sum(3) == 3.0
        assert fwt.total() == 3.0

    def test_float_weights(self) -> None:
        array = [0.1, 0.2, 0.3, 0.4]
        fwt = FenwickTree(array)

        assert abs(fwt.total() - 1.0) < 1e-9

    def test_negative_weights(self) -> None:
        fwt = FenwickTree([-1.0, -2.0, -3.0])

        assert abs(fwt.total() - (-6.0)) < 1e-9
        assert abs(fwt.prefix_sum(2) - (-3.0)) < 1e-9

    def test_mixed_positive_negative(self) -> None:
        fwt = FenwickTree([5.0, -3.0, 2.0])

        assert abs(fwt.total() - 4.0) < 1e-9

    def test_large_values(self) -> None:
        fwt = FenwickTree([1e15, 2e15, 3e15])

        assert abs(fwt.total() - 6e15) < 1e6

    def test_size_attribute(self) -> None:
        fwt = FenwickTree([1.0] * 42)

        assert fwt.size == 42

    def test_generator_input(self) -> None:
        fwt = FenwickTree(float(x) for x in range(1, 6))

        assert fwt.total() == 15.0

    def test_power_of_two_size(self) -> None:
        fwt = FenwickTree([1.0] * 8)

        assert fwt.total() == 8.0
        assert fwt.prefix_sum(4) == 4.0

    def test_non_power_of_two_size(self) -> None:
        fwt = FenwickTree([1.0] * 7)

        assert fwt.total() == 7.0
        assert fwt.prefix_sum(7) == 7.0


class TestPrefixSum:

    def test_index_zero_returns_zero(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.prefix_sum(0) == 0.0

    def test_negative_index_returns_zero(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.prefix_sum(-5) == 0.0

    def test_index_beyond_size_clamped(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.prefix_sum(100) == fwt.prefix_sum(3)

    def test_each_prefix(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0, 4.0, 5.0])

        expected = [1, 3, 6, 10, 15]
        for i, exp in enumerate(expected, start=1):
            assert fwt.prefix_sum(i) == exp

    def test_prefix_sum_monotone(self) -> None:
        fwt = FenwickTree([random.uniform(0, 10) for _ in range(50)])
        prev = 0.0

        for i in range(1, 51):
            cur = fwt.prefix_sum(i)

            assert cur >= prev - 1e-9
            prev = cur

    def test_prefix_sum_full_equals_total(self) -> None:
        fwt = FenwickTree([random.uniform(0, 5) for _ in range(20)])

        assert abs(fwt.prefix_sum(20) - fwt.total()) < 1e-9


class TestUpdate:

    def test_increase(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])
        fwt.update(2, 5.0)

        assert abs(fwt.prefix_sum(2) - 8.0) < 1e-9
        assert abs(fwt.total() - 11.0) < 1e-9

    def test_decrease(self) -> None:
        fwt = FenwickTree([5.0] * 3)
        fwt.update(1, -5.0)

        assert fwt.prefix_sum(1) == 0.0
        assert abs(fwt.total() - 10.0) < 1e-9

    def test_zero_delta_is_no_op(self) -> None:
        fwt = FenwickTree([3.0] * 3)
        before = fwt.total()
        fwt.update(2, 0.0)

        assert fwt.total() == before

    def test_sub_epsilon_delta_is_no_op(self) -> None:
        fwt = FenwickTree([1.0] * 3)
        before = fwt.total()
        fwt.update(1, 1e-13)

        assert fwt.total() == before

    def test_out_of_bounds_index_zero_is_no_op(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])
        fwt.update(0, 99.0)

        assert abs(fwt.total() - 6.0) < 1e-9

    def test_out_of_bounds_index_over_size_is_no_op(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])
        fwt.update(4, 99.0)

        assert abs(fwt.total() - 6.0) < 1e-9

    def test_update_nagative_index_is_no_op(self) -> None:
        fwt = FenwickTree([1.0, 2.0])
        fwt.update(-1, 10.0)

        assert abs(fwt.total() - 3.0) < 1e-9

    def test_repeated_updates_accumulate(self) -> None:
        fwt = FenwickTree([0.0] * 4)

        for _ in range(10):
            fwt.update(3, 1.0)

        assert abs(fwt.prefix_sum(3) - 10.0) < 1e-9

    def test_update_all_positions(self) -> None:
        fwt = FenwickTree([0.0] * 5)
        for i in range(1, 6):
            fwt.update(i, float(i))

        assert abs(fwt.total() - 15.0) < 1e-9

    def test_update_only_affects_later_prefix_sums(self) -> None:
        fwt = FenwickTree([1.0] * 4)
        fwt.update(3, 10.0)

        assert abs(fwt.prefix_sum(2) - 2.0) < 1e-9  # unaffected
        assert abs(fwt.prefix_sum(3) - 13.0) < 1e-9  # affected
        assert abs(fwt.prefix_sum(4) - 14.0) < 1e-9  # affected


class TestQuery:

    def test_basic_lookup(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0, 4.0, 5.0])

        # prefix sums : [1, 3, 6, 10, 15]
        assert fwt.query(1.0) == 1
        assert fwt.query(2.0) == 2
        assert fwt.query(3.0) == 2
        assert fwt.query(6.0) == 3
        assert fwt.query(10.0) == 4
        assert fwt.query(15.0) == 5

    def test_target_zero_returns_first(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.query(0.0) == 1

    def test_negative_target_returns_first(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.query(-999.0) == 1

    def test_target_beyond_total_clamps(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert fwt.query(9999.0) == 3

    def test_zero_total_returns_none(self) -> None:
        fwt = FenwickTree([0.0] * 3)

        assert fwt.query(1.0) is None

    def test_empty_tree_returns_none(self) -> None:
        fwt = FenwickTree([])

        assert fwt.query(1.0) is None

    def test_query_after_update(self) -> None:
        fwt = FenwickTree([1.0] * 3)
        fwt.update(2, 10.0)

        # prefix sums: [1, 12, 13]
        assert fwt.query(1.0) == 1
        assert fwt.query(2.0) == 2
        assert fwt.query(12.0) == 2
        assert fwt.query(13.0) == 3

    def test_query_at_exact_boundary(self) -> None:
        fwt = FenwickTree([1.0] * 3)

        assert fwt.query(2.0) == 2

    def test_query_just_below_boundary(self) -> None:
        fwt = FenwickTree([1.0] * 3)

        assert fwt.query(1.9999) == 2

    def test_query_just_above_boundary(self) -> None:
        fwt = FenwickTree([1.0] * 3)

        assert fwt.query(2.0001) == 3

    def test_single_element_query(self) -> None:
        fwt = FenwickTree([15.0])

        assert fwt.query(3.0) == 1
        assert fwt.query(5.0) == 1
        assert fwt.query(6.0) == 1

    def test_query_uniform_weights(self) -> None:
        fwt = FenwickTree([2.0] * 5)

        assert fwt.query(2.0) == 1
        assert fwt.query(4.0) == 2
        assert fwt.query(6.0) == 3
        assert fwt.query(8.0) == 4
        assert fwt.query(10.0) == 5

    def test_query_vs_naive_oracle(self) -> None:
        rng = random.Random(42)

        for _ in range(200):
            array = [rng.uniform(0.1, 5.0) for _ in range(rng.randint(1, 50))]
            fwt = FenwickTree(array)

            total = sum(array)

            for _ in range(20):
                target = rng.uniform(0, total)

                assert fwt.query(target) == naive_query(array, target)


class TestOracleValidation:

    def test_prefix_sum_oracle_random(self) -> None:
        rng = random.Random(0)

        for _ in range(100):
            array = [rng.uniform(0, 10) for _ in range(rng.randint(1, 100))]
            fwt = FenwickTree(array)

            prefix = list(itertools.accumulate(array))

            for i in range(1, len(array) + 1):
                assert abs(fwt.prefix_sum(i) - prefix[i - 1]) < 1e-6

    def test_prefix_sum_after_random_updates(self) -> None:
        rng = random.Random(1)

        for _ in range(50):
            n = rng.randint(5, 80)
            array = [rng.uniform(0, 5) for _ in range(n)]
            fwt = FenwickTree(array)

            for _ in range(30):
                idx = rng.randint(1, n)
                delta = rng.uniform(-2, 2)

                fwt.update(idx, delta)

                array[idx - 1] += delta

            prefix = list(itertools.accumulate(array))
            for i in range(1, n + 1):
                assert abs(fwt.prefix_sum(i) - prefix[i - 1]) < 1e-5

    def test_total_oracle(self) -> None:
        rng = random.Random(2)

        for _ in range(100):
            array = [rng.uniform(0, 10) for _ in range(50)]
            fwt = FenwickTree(array)

            assert abs(fwt.total() - sum(array)) < 1e-5


class TestQueryConsistency:

    def test_invariant_random(self) -> None:
        rng = random.Random(3)

        for _ in range(100):
            array = [rng.uniform(0.1, 5.0) for _ in range(rng.randint(2, 200))]
            fwt = FenwickTree(array)
            total = fwt.total()

            for _ in range(50):
                target = rng.uniform(1e-6, total - 1e-6)
                k = fwt.query(target)

                assert k is not None

                assert fwt.prefix_sum(k) >= target - 1e-9

                if k > 1:
                    assert fwt.prefix_sum(k - 1) < target + 1e-9

    def test_invariant_after_updates(self) -> None:
        rng = random.Random(4)
        array = [rng.uniform(0.5, 3.0) for _ in range(50)]
        fwt = FenwickTree(array)

        for _ in range(20):
            idx = rng.randint(1, 50)
            fwt.update(idx, rng.uniform(-0.4, 2.0))

        total = fwt.total()
        if total > 0:
            for _ in range(100):
                target = rng.uniform(1e-6, total - 1e-6)
                k = fwt.query(target)

                assert k is not None
                assert fwt.prefix_sum(k) >= target - 1e-9

                if k > 1:
                    assert fwt.prefix_sum(k - 1) < target + 1e-9


class TestRangeSum:

    def test_range_sum_basic(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0, 4.0, 5.0])
        # range [2, 4] = 2 + 3 + 4 = 9
        assert abs(fwt.prefix_sum(4) - fwt.prefix_sum(1) - 9.0) < 1e-9

    def test_range_sum_full(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0, 4.0, 5.0])

        assert abs(fwt.prefix_sum(5) - fwt.prefix_sum(0) - 15.0) < 1e-9

    def test_range_sum_single_element(self) -> None:
        fwt = FenwickTree([1.0, 2.0, 3.0])

        assert abs(fwt.prefix_sum(2) - fwt.prefix_sum(1) - 2.0) < 1e-9

    def test_range_sum_vs_naive(self) -> None:
        rng = random.Random(5)

        for _ in range(50):
            array = [rng.uniform(0, 10) for _ in range(30)]
            fwt = FenwickTree(array)
            l = rng.randint(1, 15)
            r = rng.randint(l, 30)
            expected = sum(array[l - 1 : r])
            got = fwt.prefix_sum(r) - fwt.prefix_sum(l - 1)

            assert abs(got - expected) < 1e-5


class TestFloatPrecision:

    def test_many_small_increments(self) -> None:
        fwt = FenwickTree([0.0])

        for _ in range(10_000):
            fwt.update(1, 0.0001)

        assert abs(fwt.total() - 1.0) < 1e-6

    def test_prefix_sum_precision_accumulate(self) -> None:
        n = 1000
        fwt = FenwickTree([0.1] * n)

        assert abs(fwt.total() - 100.0) < 1e-6

    def test_epsilon_boundary_query(self) -> None:
        weights = [1.0] * 10
        fwt = FenwickTree(weights)

        for i in range(1, 11):
            boundary = float(i)
            k = fwt.query(boundary)

            assert k is not None
            assert fwt.prefix_sum(k) >= boundary - 1e-9


# Performance tests disabled from CI due to non-deterministic runtime behavior.
# Kept for local benchmarking only.

# class TestPerformance:

#     SIZE = 1_000_000
#     THRESHOLD = 4

#     @pytest.fixture(scope="class")
#     def large_fwt(self) -> FenwickTree:
#         rng = random.Random(99)
#         array = [rng.random() for _ in range(self.SIZE)]

#         return FenwickTree(array)

#     def test_construction_speed(self) -> None:
#         rng = random.Random(7)
#         array = [rng.random() for _ in range(self.SIZE)]

#         start = time.perf_counter()
#         FenwickTree(array)
#         elapsed = time.perf_counter() - start

#         assert elapsed < self.THRESHOLD

#     def test_prefix_sum_speed(self, large_fwt) -> None:
#         start = time.perf_counter()

#         for i in range(1, self.SIZE, 200):
#             large_fwt.prefix_sum(i)

#         elapsed = time.perf_counter() - start

#         assert elapsed < self.THRESHOLD

#     def test_update_speed(self, large_fwt) -> None:
#         start = time.perf_counter()

#         for i in range(1, self.SIZE, 100):
#             large_fwt.update(i, 1.0)

#         elapsed = time.perf_counter() - start

#         assert elapsed < self.THRESHOLD

#     def test_query_speed(self, large_fwt) -> None:
#         rng = random.Random(8)
#         total = large_fwt.total()

#         start = time.perf_counter()

#         for _ in range(10_000):
#             large_fwt.query(rng.uniform(0, total))

#         elapsed = time.perf_counter() - start

#         assert elapsed < self.THRESHOLD

#     def test_mixed_operations_speed(self, large_fwt) -> None:
#         rng = random.Random(9)
#         total = large_fwt.total()

#         start = time.perf_counter()

#         for _ in range(3_000):
#             large_fwt.prefix_sum(rng.randint(1, self.SIZE))
#             large_fwt.update(rng.randint(1, self.SIZE), rng.uniform(-0.5, 0.5))
#             large_fwt.query(rng.uniform(0, total))

#         elapsed = time.perf_counter() - start

#         assert elapsed < self.THRESHOLD
