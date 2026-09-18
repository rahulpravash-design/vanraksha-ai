"""Evaluation metrics for the triage and surveillance layers.

A single accuracy number is close to meaningless for this problem. The classes
are heavily imbalanced -- most reports are routine -- so a model that predicts
"routine" forever scores well and is useless. Worse, the two error types have
completely different costs: a missed urgent case can kill an animal, while a
false alert costs a veterinary team a wasted trip.

These are the measures that actually say whether the system works:

* **Recall on the escalated classes** -- of the cases that needed a vet, how
  many were routed to one.
* **Alert precision** -- of the clusters raised, how many a reviewer confirmed.
* **Detection delay** -- how long between the first report of an event and the
  alert. A detector that is perfectly accurate three weeks late is no use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class ConfusionMatrix:
    labels: list[str]
    matrix: list[list[int]]

    @classmethod
    def build(cls, y_true: Sequence[str], y_pred: Sequence[str]) -> "ConfusionMatrix":
        if len(y_true) != len(y_pred):
            raise ValueError("y_true and y_pred must be the same length")
        labels = sorted(set(y_true) | set(y_pred))
        index = {label: i for i, label in enumerate(labels)}
        matrix = [[0] * len(labels) for _ in labels]
        for actual, predicted in zip(y_true, y_pred):
            matrix[index[actual]][index[predicted]] += 1
        return cls(labels=labels, matrix=matrix)

    def to_dict(self) -> dict[str, Any]:
        return {"labels": self.labels, "matrix": self.matrix}


@dataclass
class ClassReport:
    label: str
    support: int
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "support": self.support,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classification_report(
    y_true: Sequence[str], y_pred: Sequence[str]
) -> dict[str, Any]:
    """Per-class precision / recall / F1 plus macro and weighted averages."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    if not y_true:
        return {"classes": [], "macro_f1": 0.0, "weighted_f1": 0.0, "accuracy": 0.0}

    labels = sorted(set(y_true) | set(y_pred))
    reports: list[ClassReport] = []
    for label in labels:
        tp = sum(1 for a, p in zip(y_true, y_pred) if a == label and p == label)
        fp = sum(1 for a, p in zip(y_true, y_pred) if a != label and p == label)
        fn = sum(1 for a, p in zip(y_true, y_pred) if a == label and p != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        reports.append(
            ClassReport(label, sum(1 for a in y_true if a == label), precision, recall, f1)
        )

    total = len(y_true)
    accuracy = _safe_div(sum(1 for a, p in zip(y_true, y_pred) if a == p), total)
    macro_f1 = _safe_div(sum(r.f1 for r in reports), len(reports))
    weighted_f1 = _safe_div(sum(r.f1 * r.support for r in reports), total)

    return {
        "classes": [r.to_dict() for r in reports],
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "confusion_matrix": ConfusionMatrix.build(y_true, y_pred).to_dict(),
    }


def escalation_recall(
    y_true: Sequence[str], y_pred: Sequence[str], escalated: Sequence[str]
) -> dict[str, float]:
    """How reliably cases that needed a vet were routed to one.

    Treats the problem as binary -- escalated versus not -- because that is the
    decision the triage layer actually makes. A case moved from 'urgent' to
    'emergency' is not an error worth counting against the system; a case moved
    from 'urgent' to 'monitor' is.
    """
    escalated_set = set(escalated)
    tp = sum(1 for a, p in zip(y_true, y_pred) if a in escalated_set and p in escalated_set)
    fn = sum(1 for a, p in zip(y_true, y_pred) if a in escalated_set and p not in escalated_set)
    fp = sum(1 for a, p in zip(y_true, y_pred) if a not in escalated_set and p in escalated_set)
    tn = sum(
        1 for a, p in zip(y_true, y_pred)
        if a not in escalated_set and p not in escalated_set
    )
    recall = _safe_div(tp, tp + fn)
    precision = _safe_div(tp, tp + fp)
    return {
        "escalation_recall": round(recall, 4),
        "escalation_precision": round(precision, 4),
        "missed_escalations": fn,
        "false_escalations": fp,
        "true_escalations": tp,
        "true_routine": tn,
        "specificity": round(_safe_div(tn, tn + fp), 4),
    }


def roc_auc(y_true: Sequence[int], scores: Sequence[float]) -> float:
    """Area under the ROC curve via the rank-sum identity, ties handled.

    Equivalent to the probability that a randomly chosen positive outranks a
    randomly chosen negative.
    """
    if len(y_true) != len(scores):
        raise ValueError("y_true and scores must be the same length")
    positives = sum(1 for y in y_true if y == 1)
    negatives = len(y_true) - positives
    if positives == 0 or negatives == 0:
        return 0.5

    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        average_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1

    rank_sum = sum(r for r, y in zip(ranks, y_true) if y == 1)
    return round(
        (rank_sum - positives * (positives + 1) / 2) / (positives * negatives), 4
    )


def alert_quality(
    confirmed: int, rejected: int, missed_events: int = 0
) -> dict[str, float]:
    """Operational quality of raised alerts, as a reviewer would score them."""
    raised = confirmed + rejected
    return {
        "alerts_raised": raised,
        "confirmed": confirmed,
        "rejected": rejected,
        "alert_precision": round(_safe_div(confirmed, raised), 4),
        "false_alert_rate": round(_safe_div(rejected, raised), 4),
        "event_recall": round(_safe_div(confirmed, confirmed + missed_events), 4),
    }


def detection_delay_hours(
    event_first_report: Sequence[float], alert_raised: Sequence[float]
) -> dict[str, float]:
    """Summary of how long detection took, in hours, across events.

    Both sequences are epoch seconds, paired by event.
    """
    if len(event_first_report) != len(alert_raised):
        raise ValueError("both sequences must be the same length")
    if not event_first_report:
        return {"mean_hours": 0.0, "median_hours": 0.0, "max_hours": 0.0, "events": 0}

    delays = sorted(
        (raised - first) / 3600.0
        for first, raised in zip(event_first_report, alert_raised)
    )
    mid = len(delays) // 2
    median = delays[mid] if len(delays) % 2 else (delays[mid - 1] + delays[mid]) / 2
    return {
        "mean_hours": round(sum(delays) / len(delays), 2),
        "median_hours": round(median, 2),
        "max_hours": round(max(delays), 2),
        "events": len(delays),
    }
