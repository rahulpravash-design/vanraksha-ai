"""The field-to-response pipeline.

Each stage is useful on its own; the value is in the sequence:

    report -> normalise -> triage -> cluster -> aberration check -> alert

The stages are kept separate so that each can be tested, tuned, and replaced in
isolation, and so that a failure in surveillance never blocks triage. A farmer's
report gets a band and a recommended action even if the clustering job is down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Sequence

from .anomaly import AnomalyConfig, AnomalyDetector, AnomalyLevel, AnomalySignal
from .clustering import Cluster, ClusterConfig, ClusterPoint, GeoTemporalClusterDetector
from .models import Observation, RiskAssessment, RiskBand
from .risk import RiskEngine
from .taxonomy import SYNDROME_LABELS, normalise
from .trends import bucket_counts, counts_only

PIPELINE_VERSION = "pipeline/1.0.0"


class AlertKind(str, Enum):
    CLUSTER = "cluster"
    ABERRATION = "aberration"
    CASE = "case"


class Audience(str, Enum):
    FARMER = "farmer"
    FIELD_WORKER = "field_worker"
    VETERINARIAN = "veterinarian"
    BLOCK_ADMIN = "block_admin"
    DISTRICT_ADMIN = "district_admin"


@dataclass
class Alert:
    alert_id: str
    kind: AlertKind
    severity: float
    title: str
    body: str
    scope: str
    audiences: list[Audience]
    raised_at: datetime
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "kind": self.kind.value,
            "severity": round(self.severity, 1),
            "title": self.title,
            "body": self.body,
            "scope": self.scope,
            "audiences": [a.value for a in self.audiences],
            "raised_at": self.raised_at.isoformat(),
            "evidence": self.evidence,
        }


@dataclass
class SweepResult:
    assessments: list[RiskAssessment]
    clusters: list[Cluster]
    signals: list[AnomalySignal]
    alerts: list[Alert]
    pipeline_version: str = PIPELINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessments": [a.to_dict() for a in self.assessments],
            "clusters": [c.to_dict() for c in self.clusters],
            "signals": [s.to_dict() for s in self.signals],
            "alerts": [a.to_dict() for a in self.alerts],
            "pipeline_version": self.pipeline_version,
        }


#: Cluster severity at which the district level is notified rather than just
#: the block. Tuned so a single-village event stays local.
DISTRICT_ESCALATION_SEVERITY = 55.0


class SurveillancePipeline:
    def __init__(
        self,
        risk_engine: RiskEngine | None = None,
        cluster_config: ClusterConfig | None = None,
        anomaly_config: AnomalyConfig | None = None,
    ) -> None:
        self.risk = risk_engine or RiskEngine()
        self.clusterer = GeoTemporalClusterDetector(cluster_config)
        self.anomaly = AnomalyDetector(anomaly_config)

    # ------------------------------------------------------------------ triage

    def triage(self, observation: Observation) -> RiskAssessment:
        return self.risk.assess(observation)

    def triage_many(self, observations: Sequence[Observation]) -> list[RiskAssessment]:
        return [self.risk.assess(o) for o in observations]

    # ------------------------------------------------------------- surveillance

    def sweep(
        self,
        observations: Sequence[Observation],
        *,
        now: datetime | None = None,
        scope_label: str = "district",
        baseline_weeks: int = 10,
    ) -> SweepResult:
        """Full surveillance pass over a window of reports."""
        now = now or datetime.utcnow()
        assessments = self.triage_many(observations)
        by_id = {a.report_id: a for a in assessments}

        points = [
            self._to_point(obs, by_id.get(obs.report_id))
            for obs in observations
            if obs.latitude is not None and obs.longitude is not None
        ]
        clusters = self.clusterer.detect(points)

        signals = self._aberration_signals(
            observations, now=now, scope_label=scope_label, baseline_weeks=baseline_weeks
        )

        alerts = (
            self._cluster_alerts(clusters, now)
            + self._aberration_alerts(signals, now)
            + self._case_alerts(assessments, observations, now)
        )
        alerts.sort(key=lambda a: a.severity, reverse=True)

        return SweepResult(
            assessments=assessments, clusters=clusters, signals=signals, alerts=alerts
        )

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _to_point(obs: Observation, assessment: RiskAssessment | None) -> ClusterPoint:
        # Cluster similarity is computed over normalised codes, never raw text,
        # so that "loose motion" and "diarrhoea" land in the same cluster.
        codes = normalise(obs.symptoms).codes
        return ClusterPoint(
            report_id=obs.report_id,
            latitude=float(obs.latitude or 0.0),
            longitude=float(obs.longitude or 0.0),
            observed_at=obs.reported_at,
            symptom_codes=codes,
            species=obs.species,
            species_group=obs.species_group(),
            village_id=obs.village_id,
            animal_id=obs.animal_id,
            affected_count=obs.affected_count,
            deaths_count=obs.deaths_count,
            risk_score=assessment.score if assessment else 0.0,
        )

    def _aberration_signals(
        self,
        observations: Sequence[Observation],
        *,
        now: datetime,
        scope_label: str,
        baseline_weeks: int,
    ) -> list[AnomalySignal]:
        """One signal for the whole scope, plus one per village that reported.

        Village-level series are noisy by nature, which is what the absolute
        count floor in the detector is there to absorb.
        """
        signals: list[AnomalySignal] = []

        overall = bucket_counts(
            [o.reported_at for o in observations],
            period="week", periods=baseline_weeks, end=now.date(),
        )
        if any(p.count for p in overall):
            signals.append(
                self.anomaly.evaluate(counts_only(overall), scope=scope_label, metric="report_count")
            )

        by_village: dict[str, list[datetime]] = {}
        for obs in observations:
            if obs.village_id:
                by_village.setdefault(obs.village_id, []).append(obs.reported_at)

        for village, stamps in sorted(by_village.items()):
            series = bucket_counts(stamps, period="week", periods=baseline_weeks, end=now.date())
            signals.append(
                self.anomaly.evaluate(counts_only(series), scope=village, metric="report_count")
            )

        return [s for s in signals if s.level is not AnomalyLevel.NORMAL] or signals[:1]

    @staticmethod
    def _cluster_alerts(clusters: Sequence[Cluster], now: datetime) -> list[Alert]:
        alerts: list[Alert] = []
        for cluster in clusters:
            audiences = [Audience.VETERINARIAN, Audience.BLOCK_ADMIN]
            if cluster.severity_score >= DISTRICT_ESCALATION_SEVERITY:
                audiences.append(Audience.DISTRICT_ADMIN)
            syndrome = SYNDROME_LABELS.get(cluster.dominant_syndrome or "", "mixed")
            alerts.append(
                Alert(
                    alert_id=f"ALERT-{cluster.cluster_id}",
                    kind=AlertKind.CLUSTER,
                    severity=cluster.severity_score,
                    title=(
                        f"{syndrome} cluster: {cluster.report_count} reports across "
                        f"{len(cluster.villages) or 1} locality/localities"
                    ),
                    body=cluster.explanation,
                    scope=", ".join(cluster.villages) or "unnamed locality",
                    audiences=audiences,
                    raised_at=now,
                    evidence={
                        "cluster_id": cluster.cluster_id,
                        "report_ids": cluster.point_ids,
                        "radius_km": round(cluster.radius_km, 2),
                        "growth_ratio": round(cluster.growth_ratio, 2),
                        "deaths": cluster.death_count,
                    },
                )
            )
        return alerts

    @staticmethod
    def _aberration_alerts(signals: Sequence[AnomalySignal], now: datetime) -> list[Alert]:
        alerts: list[Alert] = []
        for signal in signals:
            if signal.level is AnomalyLevel.NORMAL:
                continue
            severity = 70.0 if signal.level is AnomalyLevel.ALERT else 45.0
            audiences = [Audience.BLOCK_ADMIN]
            if signal.level is AnomalyLevel.ALERT:
                audiences += [Audience.VETERINARIAN, Audience.DISTRICT_ADMIN]
            alerts.append(
                Alert(
                    alert_id=f"ALERT-ABR-{signal.scope.replace(' ', '-')}",
                    kind=AlertKind.ABERRATION,
                    severity=severity,
                    title=(
                        f"Reporting volume {signal.excess_ratio:.1f}x baseline in {signal.scope}"
                        if signal.excess_ratio != float("inf")
                        else f"Reporting started in {signal.scope} against a zero baseline"
                    ),
                    body=signal.explanation,
                    scope=signal.scope,
                    audiences=audiences,
                    raised_at=now,
                    evidence=signal.to_dict(),
                )
            )
        return alerts

    @staticmethod
    def _case_alerts(
        assessments: Sequence[RiskAssessment],
        observations: Sequence[Observation],
        now: datetime,
    ) -> list[Alert]:
        """Individual cases urgent enough to page someone on their own."""
        villages = {o.report_id: (o.village_id or "unknown locality") for o in observations}
        alerts: list[Alert] = []
        for assessment in assessments:
            if assessment.band.rank < RiskBand.URGENT.rank:
                continue
            caution_titles = "; ".join(c.title for c in assessment.cautions)
            audiences = [Audience.VETERINARIAN, Audience.FIELD_WORKER]
            if assessment.band is RiskBand.EMERGENCY:
                audiences += [Audience.BLOCK_ADMIN, Audience.DISTRICT_ADMIN]
            alerts.append(
                Alert(
                    alert_id=f"ALERT-CASE-{assessment.report_id}",
                    kind=AlertKind.CASE,
                    severity=60.0 + assessment.band.rank * 10.0,
                    title=f"{assessment.band.value.title()} case requires response",
                    body=(
                        f"{assessment.recommended_action} "
                        + (f"Handling precautions apply: {caution_titles}." if caution_titles else "")
                    ).strip(),
                    scope=villages.get(assessment.report_id, "unknown locality"),
                    audiences=audiences,
                    raised_at=now,
                    evidence={
                        "report_id": assessment.report_id,
                        "score": round(assessment.score, 1),
                        "band": assessment.band.value,
                        "cautions": [c.caution_id for c in assessment.cautions],
                        "response_target_hours": assessment.response_target_hours,
                    },
                )
            )
        return alerts


default_pipeline = SurveillancePipeline()
