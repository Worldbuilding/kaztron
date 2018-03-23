"""
Statistical calculations using in-place, memory-friendly algorithms.
"""
import math


class MeanVarianceAccumulator:
    def __init__(self):
        self._sum = 0
        self._count = 0
        self._m2 = 0

    @classmethod
    def from_state(cls, sum_, count, m2):
        """
        Restore this object from serialised form, for use with the :meth:`~.dump_state` method.

        .. code-block:: python

            acc = MeanVarianceAccumulator()
            # ...
            acc_state = acc.dump_state()
            # later ...
            acc = MeanVarianceAccumulator.from_state(*acc_state)
        """
        self = MeanVarianceAccumulator()
        self._sum = sum_
        self._count = count
        self._m2 = m2
        return self

    def update(self, value):
        """
        Update with a new data point.

        For the M2/variance algorithm:
        https://en.wikipedia.org/w/index.php?title=Algorithms_for_calculating_variance&oldid=824616944#Online_algorithm
        """

        prev_mean = self._sum/self._count if self._count > 0 else 0
        last_delta = value - prev_mean

        self._sum += value
        self._count += 1

        next_mean = self._sum/self._count
        new_delta = value - next_mean

        self._m2 = self._m2 + last_delta * new_delta

    @property
    def sum(self):
        return self._sum

    @property
    def count(self):
        return self._count

    @property
    def mean(self):
        if self._count > 0:
            return self._sum / self._count
        else:
            return 0

    @property
    def variance(self):
        if self._count > 1:
            return self._m2 / (self._count - 1)
        else:
            return 0

    @property
    def std_dev(self):
        return math.sqrt(self.variance)

    def dump_state(self) -> tuple:
        """
        Dump the full state of the object. Can be used with :meth:`~.from_state` to restore later;
        useful for serialisation.
        """
        return self._sum, self._count, self._m2

    def __add__(self, other: 'MeanVarianceAccumulator'):
        """
        Combine two MeanVarianceAccumulator instances together.

        Parallel algorithm:
        https://en.wikipedia.org/w/index.php?title=Algorithms_for_calculating_variance&oldid=824616944#Parallel_algorithm
        """
        if not isinstance(other, MeanVarianceAccumulator):
            raise ValueError("Expected instance of 'MeanVarianceAccumulator'")

        return MeanVarianceAccumulator.from_state(
            sum_=self.sum + other.sum,
            count=self.count + other.count,
            m2=self._m2 + other._m2 + (self.mean - other.mean) ** 2 *
                                      self.count * other.count / (self.count + other.count)
        )
