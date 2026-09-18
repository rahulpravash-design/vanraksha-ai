"""Turning raw reports into the time series the anomaly detector consumes.

Bucketing looks trivial and is not: a naive ``group by date`` silently drops
the periods where *nothing* was reported, which is exactly the information a
baseline needs. Zero-filling every empty bucket is the whole job here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Sequence

Period = str


@dataclass
class SeriesPoint:
    period_start: date
    count: float


def _floor_to_week(value: date) -> date:
    """Monday of the ISO week containing ``value``."""
    return value - timedelta(days=value.weekday())


def bucket_counts(
    timestamps: Iterable[datetime],
    *,
    period: Period = "week",
    end: date | None = None,
    periods: int = 12,
    weights: Sequence[float] | None = None,
) -> list[SeriesPoint]:
    """Bucket timestamps into consecutive periods, zero-filling the gaps.

    ``weights`` lets the same function build "animals affected per week" or
    "deaths per week" rather than only report counts.
    """
    if period not in ("day", "week"):
        raise ValueError("period must be 'day' or 'week'")

    stamps = list(timestamps)
    if weights is not None and len(weights) != len(stamps):
        raise ValueError("weights must be the same length as timestamps")

    step = timedelta(days=1 if period == "day" else 7)
    floor: Callable[[date], date] = (lambda d: d) if period == "day" else _floor_to_week

    anchor = floor(end or (max(s.date() for s in stamps) if stamps else date.today()))
    starts = [anchor - step * (periods - 1 - i) for i in range(periods)]
    index = {start: i for i, start in enumerate(starts)}

    counts = [0.0] * periods
    for position, stamp in enumerate(stamps):
        slot = index.get(floor(stamp.date()))
        if slot is not None:
            counts[slot] += weights[position] if weights is not None else 1.0

    return [SeriesPoint(period_start=start, count=count) for start, count in zip(starts, counts)]


def counts_only(points: Sequence[SeriesPoint]) -> list[float]:
    return [p.count for p in points]


def rolling_mean(values: Sequence[float], window: int = 3) -> list[float]:
    """Trailing rolling mean; shorter windows at the start rather than NaNs."""
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float] = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def linear_trend(values: Sequence[float]) -> tuple[float, float]:
    """Ordinary least-squares slope and intercept over evenly spaced points.

    Reported alongside counts so a dashboard can say "rising" rather than
    leaving a reader to eyeball a sparkline.
    """
    n = len(values)
    if n < 2:
        return 0.0, float(values[0]) if values else 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom
    return slope, mean_y - slope * mean_x


def describe_trend(values: Sequence[float]) -> str:
    """Plain-language direction for a series, for dashboards and summaries."""
    if len(values) < 3:
        return "insufficient history"
    slope, _ = linear_trend(values)
    baseline = sum(values) / len(values)
    if baseline <= 0:
        return "no reporting activity"
    relative = slope / baseline
    if relative > 0.15:
        return "rising sharply"
    if relative > 0.05:
        return "rising"
    if relative < -0.15:
        return "falling sharply"
    if relative < -0.05:
        return "falling"
    return "stable"
