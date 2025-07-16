import numpy as np

class MonotonicAxis:
    def __init__(self, slope:float, num_points:int, intercept:float=0.0):
        assert slope > 0.0
        self._slope = slope
        self._intercept = intercept
        self._num_points = num_points

    @property
    def array(self) -> np.ndarray[float]:
        return np.arange(self._num_points) * self._slope + self._intercept

    @property
    def min(self) -> float:
        return self._intercept

    @property
    def max(self) -> float:
        return (self._num_points-1) * self._slope + self._intercept

    def value_at_idx(self, idx:int) -> float:
        if idx < 0 or idx >= self._num_points:
            raise ValueError(f"{idx=} is out of range for MonotonicAxis with {self._num_points} points")
        return idx * self._slope + self._intercept

    def idx_nearest_to_value(self, value:float) -> int:
        idx = int(round((value - self._intercept) / self._slope))
        if idx < 0:
            return 0
        elif idx >= self._num_points:
            return self._num_points - 1
        else:
            return idx

    def __len__(self) -> int:
        return self._num_points
