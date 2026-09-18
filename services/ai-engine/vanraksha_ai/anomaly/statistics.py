"""Small statistical helpers, implemented without SciPy.

The engine is deliberately dependency-free so that it runs identically in the
API container, in a test harness, and in a notebook. Everything here is exact
for the small counts that field surveillance actually produces.
"""

from __future__ import annotations

import math
from typing import Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation; 0.0 for fewer than two points."""
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    var = sum((v - mu) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam).

    Counts of disease reports per area per week are the textbook case for a
    Poisson baseline, and the upper-tail probability answers exactly the
    question a surveillance officer asks: "how surprising is this week?"

    Terms are accumulated iteratively from exp(-lam) rather than via factorials,
    which keeps the result stable for the lambda values seen here.
    """
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0 if k > 0 else 1.0

    # Sum the lower tail P(X <= k-1) and complement it.
    term = math.exp(-lam)
    cdf = term
    for i in range(1, k):
        term *= lam / i
        cdf += term
        if cdf >= 1.0:
            return 0.0
    return max(0.0, min(1.0, 1.0 - cdf))


def ewma(values: Sequence[float], alpha: float = 0.3) -> list[float]:
    """Exponentially weighted moving average over a series."""
    if not values:
        return []
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out
