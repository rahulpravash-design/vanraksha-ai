import pytest

from vanraksha_ai.evaluation import (
    ConfusionMatrix,
    alert_quality,
    classification_report,
    detection_delay_hours,
    escalation_recall,
    roc_auc,
)

BANDS = ["routine", "monitor", "priority", "urgent", "emergency"]
ESCALATED = ["priority", "urgent", "emergency"]


class TestClassification:
    def test_perfect_prediction(self):
        report = classification_report(BANDS, BANDS)
        assert report["accuracy"] == 1.0
        assert report["macro_f1"] == 1.0

    def test_metrics_on_a_known_case(self):
        true = ["a", "a", "b", "b"]
        pred = ["a", "b", "b", "b"]
        report = classification_report(true, pred)
        by_label = {c["label"]: c for c in report["classes"]}
        assert by_label["a"]["precision"] == 1.0
        assert by_label["a"]["recall"] == 0.5
        assert by_label["b"]["recall"] == 1.0
        assert report["accuracy"] == 0.75

    def test_length_mismatch_is_rejected(self):
        with pytest.raises(ValueError):
            classification_report(["a"], ["a", "b"])

    def test_empty_input(self):
        assert classification_report([], [])["macro_f1"] == 0.0

    def test_confusion_matrix_rows_sum_to_support(self):
        true = ["a", "a", "b"]
        pred = ["a", "b", "b"]
        matrix = ConfusionMatrix.build(true, pred)
        assert matrix.labels == ["a", "b"]
        assert matrix.matrix == [[1, 1], [0, 1]]


class TestEscalation:
    def test_missed_escalation_is_counted(self):
        true = ["urgent", "routine", "priority"]
        pred = ["monitor", "routine", "priority"]
        result = escalation_recall(true, pred, ESCALATED)
        assert result["missed_escalations"] == 1
        assert result["escalation_recall"] == pytest.approx(0.5)

    def test_reordering_within_escalated_bands_is_not_an_error(self):
        """Moving a case from urgent to emergency is not a triage failure."""
        result = escalation_recall(["urgent"], ["emergency"], ESCALATED)
        assert result["escalation_recall"] == 1.0
        assert result["missed_escalations"] == 0

    def test_over_escalation_shows_up_as_lost_precision(self):
        result = escalation_recall(["routine", "routine"], ["urgent", "routine"], ESCALATED)
        assert result["false_escalations"] == 1
        assert result["specificity"] == pytest.approx(0.5)


class TestRanking:
    def test_perfect_separation(self):
        assert roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0

    def test_inverted_ranking(self):
        assert roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0

    def test_all_ties_is_a_coin_flip(self):
        assert roc_auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5

    def test_single_class_returns_the_uninformative_value(self):
        assert roc_auc([1, 1, 1], [0.1, 0.5, 0.9]) == 0.5

    def test_length_mismatch_is_rejected(self):
        with pytest.raises(ValueError):
            roc_auc([1, 0], [0.5])


class TestOperational:
    def test_alert_quality(self):
        result = alert_quality(confirmed=7, rejected=3, missed_events=2)
        assert result["alert_precision"] == 0.7
        assert result["false_alert_rate"] == 0.3
        assert result["event_recall"] == pytest.approx(0.7778, abs=1e-4)

    def test_alert_quality_with_no_alerts(self):
        assert alert_quality(0, 0)["alert_precision"] == 0.0

    def test_detection_delay(self):
        result = detection_delay_hours([0, 0, 0], [3600 * 6, 3600 * 12, 3600 * 36])
        assert result["median_hours"] == 12.0
        assert result["max_hours"] == 36.0
        assert result["events"] == 3

    def test_detection_delay_with_no_events(self):
        assert detection_delay_hours([], [])["events"] == 0

    def test_detection_delay_length_mismatch(self):
        with pytest.raises(ValueError):
            detection_delay_hours([0], [1, 2])
