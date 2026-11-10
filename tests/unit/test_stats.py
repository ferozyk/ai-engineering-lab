"""Unit tests for the percentile helper."""

import numpy as np
import pytest

from ai_lab.benchmarking import percentile

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
