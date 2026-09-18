import math

import pytest

from vanraksha_ai.anomaly import (
    AnomalyConfig,
    AnomalyDetector,
    AnomalyLevel,
    evaluate_series,
    ewma,
    mean,
    median,
    poisson_sf,
    stdev,
)


class TestStatistics:
    @pytest.mark.parametrize(
        "k,lam,expected",
        [
            (1, 1.0, 0.632121),   # 1 - e^-1
            (5, 2.0, 0.052653),
            (3, 3.0, 0.576810),
            (10, 1.0, 0.000001),
        ],
    )
    def test_poisson_upper_tail_matches_known_values(self, k, lam, expected):
        assert poisson_sf(k, lam) == pytest.approx(expected, abs=1e-5)

    def test_poisson_edge_cases(self):
        assert poisson_sf(0, 5.0) == 1.0     # P(X >= 0) is certain
        assert poisson_sf(-1, 5.0) == 1.0
        assert poisson_sf(3, 0.0) == 0.0     # a zero-rate process yields nothing

    def test_poisson_is_monotonic_in_k(self):
        values = [poisson_sf(k, 4.0) for k in range(1, 12)]
        assert all(a >= b for a, b in zip(values, values[1:]))

    def test_mean_stdev_median(self):
        assert mean([1, 2, 3, 4]) == 2.5
        assert stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.13809, abs=1e-4)
        assert stdev([5]) == 0.0
        assert median([3, 1, 2]) == 2
        assert median([4, 1, 2, 3]) == 2.5
        assert mean([]) == 0.0

    def test_ewma_shape_and_bounds(self):
        smoothed = ewma([10, 10, 10, 10], 0.5)
        assert smoothed == [10, 10, 10, 10]
        rising = ewma([0, 10], 0.5)
        assert rising[-1] == pytest.approx(5.0)
        assert ewma([]) == []


class TestDetector:
    def test_stable_reporting_is_not_an_alert(self):
        signal = evaluate_series([4, 5, 4, 6, 5, 4, 5, 5], scope="V-Stable")
        assert signal.level is AnomalyLevel.NORMAL

    def test_a_clear_spike_alerts(self):
        signal = evaluate_series([2, 3, 2, 3, 2, 4, 3, 16], scope="V-Spike")
        assert signal.level is AnomalyLevel.ALERT
        assert signal.excess_ratio > 4
        assert signal.p_value < 0.01

    def test_a_gradual_rise_is_at_least_a_watch(self):
        signal = evaluate_series([2, 2, 3, 3, 4, 5, 6, 9], scope="V-Creep")
        assert signal.level in (AnomalyLevel.WATCH, AnomalyLevel.ALERT)

    def test_tiny_absolute_counts_never_alert(self):
        """A near-zero baseline makes any rise look spectacular. The absolute
        floor is what stops one extra report becoming an outbreak warning."""
        signal = evaluate_series([0, 0, 0, 0, 0, 0, 0, 2], scope="V-Quiet")
        assert signal.level is AnomalyLevel.NORMAL

    def test_a_modest_rise_over_a_high_baseline_is_not_an_alert(self):
        signal = evaluate_series([40, 42, 38, 41, 39, 40, 41, 46], scope="V-Busy")
        assert signal.level is AnomalyLevel.NORMAL

    def test_a_drop_in_reporting_is_not_an_alert(self):
        signal = evaluate_series([10, 11, 9, 10, 12, 10, 11, 2], scope="V-Silent")
        assert signal.level is AnomalyLevel.NORMAL

    def test_insufficient_history_is_reported_honestly(self):
        signal = evaluate_series([8], scope="V-New")
        assert signal.level is AnomalyLevel.WATCH
        assert "not enough history" in signal.explanation
        assert signal.p_value == 1.0

    def test_insufficient_history_with_a_small_count_stays_quiet(self):
        assert evaluate_series([2], scope="V-New").level is AnomalyLevel.NORMAL

    def test_empty_series_is_rejected(self):
        with pytest.raises(ValueError):
            evaluate_series([])

    def test_explanation_always_states_observed_and_expected(self):
        signal = evaluate_series([3, 4, 3, 4, 3, 4, 3, 15], scope="V-Talk")
        assert "15" in signal.explanation
        assert "baseline" in signal.explanation

    def test_explanation_handles_a_zero_baseline_without_printing_inf(self):
        signal = evaluate_series([0, 0, 0, 0, 0, 0, 0, 9], scope="V-Fresh")
        assert "inf" not in signal.explanation.lower()

    def test_thresholds_are_configurable(self):
        series = [3, 3, 3, 3, 3, 3, 3, 7]
        lenient = AnomalyDetector(AnomalyConfig(min_count=20)).evaluate(series, scope="s")
        strict = AnomalyDetector(AnomalyConfig(min_count=1, watch_p=0.9)).evaluate(series, scope="s")
        assert lenient.level is AnomalyLevel.NORMAL
        assert strict.level.rank >= AnomalyLevel.WATCH.rank

    def test_serialisation_is_json_safe(self):
        import json

        payload = evaluate_series([2, 3, 2, 3, 2, 4, 3, 16], scope="V").to_dict()
        assert json.loads(json.dumps(payload))["level"] == "alert"
        assert not math.isinf(payload["excess_ratio"])

    def test_zero_baseline_serialises_as_null_not_infinity(self):
        """`Infinity` is not valid JSON; a browser's JSON.parse rejects it."""
        import json

        signal = evaluate_series([0, 0, 0, 0, 0, 0, 0, 12], scope="V-Fresh")
        assert math.isinf(signal.excess_ratio)
        payload = signal.to_dict()
        assert payload["excess_ratio"] is None
        assert payload["expected"] == 0.0
        json.loads(
            json.dumps(payload),
            parse_constant=lambda c: pytest.fail(f"non-JSON constant emitted: {c}"),
        )
