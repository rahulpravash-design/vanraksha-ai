"""Time-series construction and trend description."""

from .series import (
    SeriesPoint,
    bucket_counts,
    counts_only,
    describe_trend,
    linear_trend,
    rolling_mean,
)

__all__ = [
    "SeriesPoint", "bucket_counts", "counts_only",
    "rolling_mean", "linear_trend", "describe_trend",
]
