from collections.abc import Iterable


class FenwickTree:
    """
    Fenwick Tree (Binary Indexed Tree).

    Features:
        - O(log n) prefix sum
        - O(log n) point update
        - O(log n) weighted selection (lower-bound query)

    Safety improvements:
        - Safe handling of zero or negative totals
        - Stable handling of small floating-point deltas
    """

    def __init__(self, array: Iterable[float]) -> None:
        """
        Initialize a Fenwick Tree from an iterable of weights.

        Args:
            array: Initial element weights.
        """
        array = list(array)

        self.size = len(array)
        self.tree = [0.0] * (self.size + 1)

        self._construct(array)

    def _construct(self, array: list[float]) -> None:
        """
        Build the internal tree from the provided weights.

        Args:
            array: Initial element weights.
        """
        for index, value in enumerate(array, start=1):
            if value != 0:
                self.update(index, value)

    def update(self, index: int, delta: float) -> None:
        """
        Apply a delta to a single element.

        Args:
            index: 1-based element index.
            delta: Amount to add or subtract.
        """
        if index < 1 or index > self.size:
            return

        if abs(delta) < 1e-12:
            return

        while index <= self.size:
            self.tree[index] += delta
            index += index & -index

    def prefix_sum(self, index: int) -> float:
        """
        Return the cumulative sum from position 1 through `index`.

        Args:
            index: 1-based inclusive upper bound.

        Returns:
            Sum of all values in range [1, index].
        """
        if index < 1:
            return 0.0

        if index > self.size:
            index = self.size

        result = 0.0

        while index > 0:
            result += self.tree[index]
            index -= index & -index

        return result

    def total(self) -> float:
        """Returns the cumulative sum of all elements."""
        return self.prefix_sum(self.size)

    def query(self, target: float) -> int | None:
        """
        Locate the smallest index whose cumulative sum reaches `target`.

        Args:
            target: Desired cumulative sum threshold.

        Returns:
            The 1-based index whose cumulative sum reaches the target.
            Returns `None` if the tree is empty or its total is non-positive.
            If the target exceeds the total, returns the last index.
        """
        if self.size == 0:
            return None

        if target <= 0:
            return 1

        total = self.total()

        if total <= 0:
            return None

        if target > total:
            return self.size

        indx = 0
        step = 1 << (self.size.bit_length() - 1)

        while step > 0:
            next_indx = indx + step

            if next_indx <= self.size and self.tree[next_indx] < target:
                target -= self.tree[next_indx]
                indx = next_indx

            step >>= 1

        return indx + 1
