"""Metrics for judging whether the triage and surveillance layers work."""

from .metrics import (
    ClassReport,
    ConfusionMatrix,
    alert_quality,
    classification_report,
    detection_delay_hours,
    escalation_recall,
    roc_auc,
)

__all__ = [
    "ConfusionMatrix", "ClassReport", "classification_report",
    "escalation_recall", "roc_auc", "alert_quality", "detection_delay_hours",
]
