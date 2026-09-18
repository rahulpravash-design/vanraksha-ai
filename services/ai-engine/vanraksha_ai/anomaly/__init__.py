"""Aberration detection over surveillance time series."""

from .detector import (
    DETECTOR_VERSION,
    AnomalyConfig,
    AnomalyDetector,
    AnomalyLevel,
    AnomalySignal,
    evaluate_series,
)
from .statistics import ewma, mean, median, poisson_sf, stdev

__all__ = [
    "AnomalyDetector", "AnomalyConfig", "AnomalySignal", "AnomalyLevel",
    "evaluate_series", "DETECTOR_VERSION",
    "poisson_sf", "ewma", "mean", "stdev", "median",
]
