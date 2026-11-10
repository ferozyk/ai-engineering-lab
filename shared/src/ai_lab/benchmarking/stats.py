"""Small statistics helpers for benchmark results."""

from collections.abc import Sequence


def percentile(values: Sequence[float], q: float) -> float:
    """The ``q``-th percentile (0-100) with linear interpolation between ranks.

    Same semantics as ``numpy.percentile(..., method="linear")``. An empty input raises
    ``ValueError``.
    """
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)
