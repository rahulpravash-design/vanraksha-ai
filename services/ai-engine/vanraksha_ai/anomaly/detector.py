"""Aberration detection over report-count time series.

Cluster detection answers "are these reports related?". This module answers the
complementary question: "is the *volume* of reporting in this area unusual for
this area?" -- which catches events that cluster detection misses, such as a
slow rise spread thinly across a whole block.

Two independent signals are computed and combined, because each fails in a way
the other covers:

* **Poisson exceedance** against a trailing baseline. Strong when history is
  stable; over-sensitive when the baseline is near zero, so a minimum absolute
  count gate is applied.
* **EWMA control limit**, the classical process-control approach. Robust to a
  drifting baseline, slower to react to a single sharp spike.

Both report the numbers that produced them, so an alert can be argued with.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from .statistics import ewma, mean, poisson_sf, stdev

DETECTOR_VERSION = "anomaly-detector/1.1.0"


class AnomalyLevel(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    ALERT = "alert"

    @property
    def rank(self) -> int:
        return {"normal": 0, "watch": 1, "alert": 2}[self.value]


@dataclass
class AnomalyConfig:
    #: Trailing periods used to build the baseline.
    baseline_periods: int = 8
    #: Poisson upper-tail probability below which the period is an alert.
    alert_p: float = 0.01
    watch_p: float = 0.05
    #: EWMA smoothing factor and control-limit width in baseline sigmas.
    ewma_alpha: float = 0.3
    ewma_sigma: float = 3.0
    #: Absolute floor. Two reports where one is normal is not an outbreak, no
    #: matter what the arithmetic says about a near-zero baseline.
    min_count: int = 3
    #: Minimum ratio to baseline before a signal is considered at all.
    min_excess_ratio: float = 1.5


@dataclass
class AnomalySignal:
    scope: str
    metric: str
    observed: float
    expected: float
    excess_ratio: float
    p_value: float
    ewma_value: float
    ewma_limit: float
    level: AnomalyLevel
    explanation: str
    detector_version: str = DETECTOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        # An infinite ratio is a real outcome (a zero baseline), but literal
        # Infinity is not valid JSON -- browsers reject it outright. It is
        # emitted as null, with the zero baseline readable from `expected`.
        ratio = self.excess_ratio
        return {
            "scope": self.scope,
            "metric": self.metric,
            "observed": self.observed,
            "expected": round(self.expected, 2),
            "excess_ratio": None if math.isinf(ratio) or math.isnan(ratio) else round(ratio, 2),
            "p_value": round(self.p_value, 5),
            "ewma_value": round(self.ewma_value, 2),
            "ewma_limit": round(self.ewma_limit, 2),
            "level": self.level.value,
            "explanation": self.explanation,
            "detector_version": self.detector_version,
        }


class AnomalyDetector:
    def __init__(self, config: AnomalyConfig | None = None) -> None:
        self.config = config or AnomalyConfig()

    def evaluate(
        self,
        series: Sequence[float],
        *,
        scope: str = "unspecified",
        metric: str = "report_count",
    ) -> AnomalySignal:
        """Assess the final value of ``series`` against the periods before it.

        ``series`` is ordered oldest to newest and must contain the current
        period as its last element.
        """
        if not series:
            raise ValueError("evaluate() requires at least the current period")

        observed = float(series[-1])
        history = [float(v) for v in series[:-1]][-self.config.baseline_periods:]

        if len(history) < 2:
            return self._insufficient_history(scope, metric, observed, history)

        expected = mean(history)
        sigma = stdev(history)
        ratio = observed / expected if expected > 0 else float("inf") if observed else 1.0

        p_value = poisson_sf(int(round(observed)), max(expected, 1e-9))
        smoothed = ewma(list(history) + [observed], self.config.ewma_alpha)[-1]
        # Control limit for an EWMA statistic: the variance of the smoothed
        # series is alpha/(2-alpha) times the variance of the raw series.
        alpha = self.config.ewma_alpha
        ewma_sigma = sigma * ((alpha / (2 - alpha)) ** 0.5)
        limit = expected + self.config.ewma_sigma * ewma_sigma

        level = self._level(observed, expected, ratio, p_value, smoothed, limit)
        return AnomalySignal(
            scope=scope,
            metric=metric,
            observed=observed,
            expected=expected,
            excess_ratio=ratio,
            p_value=p_value,
            ewma_value=smoothed,
            ewma_limit=limit,
            level=level,
            explanation=self._explain(
                scope, metric, observed, expected, ratio, p_value, smoothed, limit, level,
                len(history),
            ),
        )

    # ---------------------------------------------------------------- internals

    def _level(
        self, observed: float, expected: float, ratio: float,
        p_value: float, smoothed: float, limit: float,
    ) -> AnomalyLevel:
        cfg = self.config
        # Gates first: both guard against the near-zero-baseline failure mode
        # where a jump from 0.2 to 2 looks statistically spectacular.
        if observed < cfg.min_count:
            return AnomalyLevel.NORMAL
        if ratio < cfg.min_excess_ratio:
            return AnomalyLevel.NORMAL

        poisson_alert = p_value <= cfg.alert_p
        ewma_alert = smoothed > limit and limit > 0

        if poisson_alert and ewma_alert:
            return AnomalyLevel.ALERT
        if poisson_alert or ewma_alert or p_value <= cfg.watch_p:
            return AnomalyLevel.WATCH
        return AnomalyLevel.NORMAL

    def _insufficient_history(
        self, scope: str, metric: str, observed: float, history: Sequence[float]
    ) -> AnomalySignal:
        # With no baseline the honest answer is "unknown", not "normal" and not
        # "alert". A raw count well above the floor still earns a watch so that
        # a newly onboarded village is not invisible for its first two weeks.
        level = (
            AnomalyLevel.WATCH
            if observed >= max(self.config.min_count * 2, 6)
            else AnomalyLevel.NORMAL
        )
        return AnomalySignal(
            scope=scope,
            metric=metric,
            observed=observed,
            expected=mean(list(history)) if history else 0.0,
            excess_ratio=1.0,
            p_value=1.0,
            ewma_value=observed,
            ewma_limit=0.0,
            level=level,
            explanation=(
                f"{scope}: {observed:.0f} {metric.replace('_', ' ')} recorded, but only "
                f"{len(history)} earlier period(s) are available. There is not enough history "
                "to say whether this is unusual; the baseline will firm up as reporting continues."
            ),
        )

    @staticmethod
    def _explain(
        scope: str, metric: str, observed: float, expected: float, ratio: float,
        p_value: float, smoothed: float, limit: float, level: AnomalyLevel,
        history_len: int,
    ) -> str:
        ratio_text = (
            "against a baseline of effectively zero" if ratio == float("inf")
            else f"{ratio:.1f}x the usual level"
        )
        head = (
            f"{scope}: {observed:.0f} {metric.replace('_', ' ')} this period against a "
            f"{history_len}-period baseline of {expected:.1f}"
        )
        if level == AnomalyLevel.NORMAL:
            if observed < 3:
                reason = (
                    " The absolute count is below the floor at which a rise is treated as"
                    " meaningful, whatever the ratio to baseline suggests."
                )
            elif ratio < 1.5:
                reason = " Reporting is close to the usual level for this scope."
            else:
                reason = " The rise is not large enough to separate from normal variation."
            return f"{head}. Within the expected range ({ratio_text}, p={p_value:.3f}).{reason}"
        direction = "above" if smoothed > limit else "within"
        return (
            f"{head} -- {ratio_text}. The chance of seeing at least this many "
            f"reports if nothing had changed is about {p_value * 100:.1f}%, and the smoothed "
            f"trend ({smoothed:.1f}) is {direction} the control limit of {limit:.1f}."
        )


def evaluate_series(
    series: Sequence[float], *, scope: str = "unspecified", metric: str = "report_count",
    config: AnomalyConfig | None = None,
) -> AnomalySignal:
    return AnomalyDetector(config).evaluate(series, scope=scope, metric=metric)
