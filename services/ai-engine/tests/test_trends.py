from datetime import date, datetime, timedelta

import pytest

from vanraksha_ai.trends import (
    bucket_counts,
    counts_only,
    describe_trend,
    linear_trend,
    rolling_mean,
)


def stamps(*days: int, start=datetime(2026, 3, 2)):
    return [start + timedelta(days=d) for d in days]


class TestBucketing:
    def test_empty_periods_are_zero_filled(self):
        """The whole point: a baseline needs the weeks where nothing happened."""
        # 2026-03-02 is a Monday, so both stamps fall in the first bucket and
        # the three quiet weeks after it must still be present as zeros.
        points = bucket_counts(stamps(0, 1), period="week", periods=4, end=date(2026, 3, 23))
        assert counts_only(points) == [2.0, 0.0, 0.0, 0.0]
        assert [p.period_start.isoformat() for p in points] == [
            "2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23",
        ]

    def test_reports_spread_across_weeks_land_in_the_right_buckets(self):
        points = bucket_counts(
            stamps(0, 8, 8, 15), period="week", periods=3, end=date(2026, 3, 16)
        )
        assert counts_only(points) == [1.0, 2.0, 1.0]

    def test_weeks_start_on_monday(self):
        points = bucket_counts(stamps(0), period="week", periods=1, end=date(2026, 3, 5))
        assert points[0].period_start.weekday() == 0

    def test_daily_bucketing(self):
        points = bucket_counts(stamps(0, 0, 2), period="day", periods=3, end=date(2026, 3, 4))
        assert counts_only(points) == [2.0, 0.0, 1.0]

    def test_timestamps_outside_the_window_are_dropped(self):
        points = bucket_counts(stamps(-400, 0), period="week", periods=2, end=date(2026, 3, 2))
        assert sum(counts_only(points)) == 1.0

    def test_weights_build_other_metrics(self):
        points = bucket_counts(
            stamps(0, 1), period="week", periods=1, end=date(2026, 3, 2), weights=[3.0, 4.0]
        )
        assert counts_only(points) == [7.0]

    def test_mismatched_weights_are_rejected(self):
        with pytest.raises(ValueError):
            bucket_counts(stamps(0, 1), weights=[1.0])

    def test_invalid_period_is_rejected(self):
        with pytest.raises(ValueError):
            bucket_counts(stamps(0), period="month")

    def test_no_timestamps_still_returns_a_full_window(self):
        assert len(bucket_counts([], periods=6, end=date(2026, 3, 2))) == 6


class TestTrend:
    def test_rolling_mean_uses_short_windows_at_the_start(self):
        assert rolling_mean([1, 2, 3, 4], window=2) == [1.0, 1.5, 2.5, 3.5]

    def test_rolling_mean_rejects_a_bad_window(self):
        with pytest.raises(ValueError):
            rolling_mean([1, 2], window=0)

    def test_linear_trend_on_a_straight_line(self):
        slope, intercept = linear_trend([2, 4, 6, 8])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(2.0)

    def test_linear_trend_on_a_flat_line(self):
        assert linear_trend([5, 5, 5, 5])[0] == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "series,expected",
        [
            ([1, 2, 4, 8, 16], "rising sharply"),
            ([10, 10, 10, 10, 10], "stable"),
            ([16, 8, 4, 2, 1], "falling sharply"),
            ([0, 0, 0, 0], "no reporting activity"),
            ([1, 2], "insufficient history"),
        ],
    )
    def test_describe_trend(self, series, expected):
        assert describe_trend(series) == expected
