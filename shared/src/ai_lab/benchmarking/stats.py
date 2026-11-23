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


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for a proportion (default: 95%, ``z = 1.96``).

    Unlike the normal approximation it stays inside [0, 1] and behaves for small ``n`` and for
    rates of 0 or 1. ``n == 0`` raises ``ValueError`` because no rate exists.
    """
    if n <= 0:
        raise ValueError("wilson_interval needs at least one trial")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    margin = z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)
