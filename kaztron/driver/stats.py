"""
Statistical calculations using in-place, memory-friendly algorithms.
"""
import math


class MeanVarianceAccumulator:
    def __init__(self, sum_=0, count=0, m2=0):
        """
        Constructor.

         Can be used to restore the accumulator from a  :meth:`~.dump_state`:

        .. code-block:: python

            acc = MeanVarianceAccumulator()
            # ...
            acc_state = acc.dump()
            # later ...
            acc = MeanVarianceAccumulator(*acc_state)
        """
        self.sum = sum_
        self.count = count
        self.m2 = m2

    def update(self, value):
        """
        Update with a new data point.

        For the M2/variance algorithm:
        https://en.wikipedia.org/w/index.php?title=Algorithms_for_calculating_variance&oldid=824616944#Online_algorithm
        """

        prev_mean = self.sum / self.count if self.count > 0 else 0
        last_delta = value - prev_mean

        self.sum += value
        self.count += 1

        next_mean = self.sum / self.count
        new_delta = value - next_mean

        self.m2 = self.m2 + last_delta * new_delta

    @property
    def mean(self):
        if self.count > 0:
            return self.sum / self.count
        else:
            return 0

    @property
    def variance(self):
        if self.count > 1:
            return self.m2 / (self.count - 1)
        else:
            return 0

    @property
    def std_dev(self):
        return math.sqrt(self.variance)

    def dump_state(self) -> tuple:
        """
        Dump the full state of the object. Can be restored with the constructor,
        useful for serialisation.
        """
        return self.sum, self.count, self.m2

    def __add__(self, other: 'MeanVarianceAccumulator'):
        """
        Combine two MeanVarianceAccumulator instances together.

        Parallel algorithm:
        https://en.wikipedia.org/w/index.php?title=Algorithms_for_calculating_variance&oldid=824616944#Parallel_algorithm
        """
        if not isinstance(other, MeanVarianceAccumulator):
            raise ValueError("Expected instance of 'MeanVarianceAccumulator'")

        return MeanVarianceAccumulator(
            sum_=self.sum + other.sum,
            count=self.count + other.count,
            m2=(self.m2 + other.m2 + (self.mean - other.mean) ** 2 *
                self.count * other.count / (self.count + other.count))
        )
