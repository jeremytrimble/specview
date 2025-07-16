from specview.monotonic_axis import MonotonicAxis
import pytest
import numpy as np

def test_monotonic_axis():
    # Test basic properties
    axis = MonotonicAxis(slope=2.0, num_points=5, intercept=1.0)
    assert np.array_equal(axis.array, np.array([1.0, 3.0, 5.0, 7.0, 9.0]))
    assert axis.min == 1.0
    assert axis.max == 9.0

    # Test value at index
    assert axis.value_at_idx(0) == 1.0
    assert axis.value_at_idx(4) == 9.0

    # Test nearest index to value
    assert axis.idx_nearest_to_value(3.5) == 1
    assert axis.idx_nearest_to_value(10.0) == 4
    assert axis.idx_nearest_to_value(0.5) == 0
    assert axis.idx_nearest_to_value(1.0) == 0
    assert axis.idx_nearest_to_value(9.0) == 4

    # Test out of range index
    with pytest.raises(ValueError):
        axis.value_at_idx(-1)

    with pytest.raises(ValueError):
        axis.value_at_idx(5)