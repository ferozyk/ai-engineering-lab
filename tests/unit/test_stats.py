"""Unit tests for the percentile helper."""

import numpy as np
import pytest

from ai_lab.benchmarking import percentile, wilson_interval

pytestmark = pytest.mark.unit


def test_known_values() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([10.0], 95) == 10.0
    assert percentile([1, 2, 3, 4, 5], 0) == 1.0
    assert percentile([1, 2, 3, 4, 5], 100) == 5.0


def test_matches_numpy_linear() -> None:
    values = [3.2, 1.1, 9.5, 4.4, 7.0, 2.2]
    for q in (5, 25, 50, 95):
        assert percentile(values, q) == pytest.approx(float(np.percentile(values, q)))


def test_errors() -> None:
    with pytest.raises(ValueError, match="empty"):
        percentile([], 50)
    with pytest.raises(ValueError, match="between"):
        percentile([1.0], 101)


def test_wilson_interval_known_values() -> None:
    low, high = wilson_interval(8, 20)
    assert low == pytest.approx(0.2188, abs=1e-3)
    assert high == pytest.approx(0.6134, abs=1e-3)


def test_wilson_interval_stays_inside_zero_and_one() -> None:
    low, high = wilson_interval(0, 20)
    assert low == 0.0 and 0.1 < high < 0.2
    low, high = wilson_interval(20, 20)
    assert high == 1.0 and 0.8 < low < 0.9


def test_wilson_interval_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="at least one"):
        wilson_interval(0, 0)
    with pytest.raises(ValueError, match="between 0 and n"):
        wilson_interval(5, 4)
