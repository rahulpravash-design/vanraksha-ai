"""Geo-temporal-syndromic cluster detection.

The question this answers is deliberately not "which disease is this?" but
"is something unusual happening in one place right now?" -- which is the
question a block veterinary officer can actually act on, and the one that can
be answered honestly from field reports alone.

Two reports are *neighbours* when all three of the following hold:

    * they are within ``radius_km`` of each other,
    * they were observed within ``window_hours`` of each other,
    * their syndromic profiles overlap by at least ``min_similarity``.

Clusters are then the density-connected components over that neighbourhood
relation -- DBSCAN, with a domain-specific neighbourhood predicate instead of
a plain distance ball. Reports that never reach ``min_reports`` neighbours stay
unclustered rather than being forced into the nearest group, because a false
cluster costs a veterinary team a wasted field visit.

The implementation is O(n^2) in the number of candidate reports. Detection runs
over a trailing window for one district at a time, which keeps n in the low
thousands; a spatial index is the documented next step if that stops holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Sequence

from .. import taxonomy
from .geo import bounding_radius_km, centroid, haversine_km, jaccard

DETECTOR_VERSION = "cluster-detector/1.1.0"

_NOISE = -1
_UNVISITED = -2


@dataclass
class ClusterPoint:
    """One report as the detector sees it."""

    report_id: str
    latitude: float
    longitude: float
    observed_at: datetime
    symptom_codes: list[str] = field(default_factory=list)
    species: str = "cattle"
    species_group: str = "bovine"
    village_id: str | None = None
    animal_id: str | None = None
    affected_count: int = 1
    deaths_count: int = 0
    risk_score: float = 0.0

    @property
    def syndromes(self) -> list[str]:
        return taxonomy.syndromes_for(self.symptom_codes)


@dataclass
class ClusterConfig:
    """Detection parameters.

    The defaults come from the sweep in ``ml/evaluate_detector.py`` against
    scenarios where the answer is known. On that data, raising ``min_reports``
    from three to four cut false alerts on outbreak-free districts from 1.43
    per scenario to 0.13 -- a 5.8x reduction -- while still finding every
    injected event, at the cost of about a day of median detection delay.
    Narrowing the window from seven days to five cut them further at no cost
    to detection at all.

    That trade is worth making because the two errors are not symmetrical: a
    false cluster spends a veterinary team's day and, repeated, teaches a
    block officer to ignore the system, after which its detection rate stops
    mattering.

    **These values are density-dependent.** They were tuned at roughly 0.3
    background reports per village per day. A district reporting far more or
    far less should re-run the sweep rather than inherit them -- see
    docs/05-ai/clustering.md.
    """

    radius_km: float = 5.0
    window_hours: float = 120.0          # five days
    min_reports: int = 4                 # DBSCAN minPts, including the core point
    min_similarity: float = 0.34         # share at least ~1 syndrome in 3
    #: When true, reports from species that do not share a disease pool are
    #: never treated as neighbours (a poultry death is not evidence about goats).
    respect_species_group: bool = True


@dataclass
class Cluster:
    cluster_id: str
    point_ids: list[str]
    centroid_lat: float
    centroid_lon: float
    radius_km: float
    first_seen: datetime
    last_seen: datetime
    report_count: int
    animal_count: int
    death_count: int
    villages: list[str]
    species: list[str]
    dominant_syndrome: str | None
    syndrome_profile: dict[str, int]
    top_symptoms: list[tuple[str, int]]
    mean_risk_score: float
    #: 0-100 composite of size, growth, mortality and clinical severity.
    severity_score: float
    #: Reports in the most recent quarter of the window vs the rest.
    growth_ratio: float
    explanation: str
    detector_version: str = DETECTOR_VERSION

    @property
    def duration_hours(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds() / 3600.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "point_ids": self.point_ids,
            "centroid": {"lat": round(self.centroid_lat, 6), "lon": round(self.centroid_lon, 6)},
            "radius_km": round(self.radius_km, 3),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "duration_hours": round(self.duration_hours, 1),
            "report_count": self.report_count,
            "animal_count": self.animal_count,
            "death_count": self.death_count,
            "villages": self.villages,
            "species": self.species,
            "dominant_syndrome": self.dominant_syndrome,
            "syndrome_profile": self.syndrome_profile,
            "top_symptoms": [{"code": c, "count": n} for c, n in self.top_symptoms],
            "mean_risk_score": round(self.mean_risk_score, 1),
            "severity_score": round(self.severity_score, 1),
            "growth_ratio": round(self.growth_ratio, 2),
            "explanation": self.explanation,
            "detector_version": self.detector_version,
        }


class GeoTemporalClusterDetector:
    def __init__(self, config: ClusterConfig | None = None) -> None:
        self.config = config or ClusterConfig()

    # -------------------------------------------------------------- public API

    def detect(self, points: Sequence[ClusterPoint]) -> list[Cluster]:
        """Run detection over a set of reports, newest-window first."""
        if len(points) < self.config.min_reports:
            return []

        ordered = sorted(points, key=lambda p: p.observed_at)
        neighbours = self._build_neighbourhoods(ordered)
        labels = self._dbscan(ordered, neighbours)

        grouped: dict[int, list[ClusterPoint]] = {}
        for point, label in zip(ordered, labels):
            if label >= 0:
                grouped.setdefault(label, []).append(point)

        clusters = [
            self._summarise(f"CL-{index + 1:03d}", members)
            for index, (_, members) in enumerate(sorted(grouped.items()))
        ]
        clusters.sort(key=lambda c: c.severity_score, reverse=True)
        # Re-key so the identifier reflects the presented order.
        for index, cluster in enumerate(clusters):
            cluster.cluster_id = f"CL-{index + 1:03d}"
        return clusters

    def is_neighbour(self, a: ClusterPoint, b: ClusterPoint) -> bool:
        cfg = self.config
        if cfg.respect_species_group and a.species_group != b.species_group:
            return False
        hours = abs((a.observed_at - b.observed_at).total_seconds()) / 3600.0
        if hours > cfg.window_hours:
            return False
        if haversine_km(a.latitude, a.longitude, b.latitude, b.longitude) > cfg.radius_km:
            return False
        return jaccard(a.syndromes, b.syndromes) >= cfg.min_similarity

    # ---------------------------------------------------------------- internals

    def _build_neighbourhoods(self, points: Sequence[ClusterPoint]) -> list[list[int]]:
        n = len(points)
        neighbours: list[list[int]] = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if self.is_neighbour(points[i], points[j]):
                    neighbours[i].append(j)
                    neighbours[j].append(i)
        return neighbours

    def _dbscan(self, points: Sequence[ClusterPoint], neighbours: list[list[int]]) -> list[int]:
        labels = [_UNVISITED] * len(points)
        next_label = 0

        for i in range(len(points)):
            if labels[i] != _UNVISITED:
                continue
            # +1 because a point is a member of its own neighbourhood.
            if len(neighbours[i]) + 1 < self.config.min_reports:
                labels[i] = _NOISE
                continue

            labels[i] = next_label
            queue = list(neighbours[i])
            seen = set(queue)
            while queue:
                j = queue.pop(0)
                if labels[j] == _NOISE:
                    # Border point: reachable, but not dense enough to expand.
                    labels[j] = next_label
                    continue
                if labels[j] != _UNVISITED:
                    continue
                labels[j] = next_label
                if len(neighbours[j]) + 1 >= self.config.min_reports:
                    for k in neighbours[j]:
                        if k not in seen:
                            seen.add(k)
                            queue.append(k)
            next_label += 1

        return labels

    def _summarise(self, cluster_id: str, members: list[ClusterPoint]) -> Cluster:
        coords = [(p.latitude, p.longitude) for p in members]
        clat, clon = centroid(coords)
        first = min(p.observed_at for p in members)
        last = max(p.observed_at for p in members)

        symptom_counts: dict[str, int] = {}
        syndrome_counts: dict[str, int] = {}
        for point in members:
            for code in point.symptom_codes:
                symptom_counts[code] = symptom_counts.get(code, 0) + 1
            for syndrome in point.syndromes:
                syndrome_counts[syndrome] = syndrome_counts.get(syndrome, 0) + 1

        top_symptoms = sorted(symptom_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        dominant = (
            max(syndrome_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if syndrome_counts else None
        )

        villages = sorted({p.village_id for p in members if p.village_id})
        species = sorted({p.species for p in members})
        animals = sum(p.affected_count for p in members)
        deaths = sum(p.deaths_count for p in members)
        mean_risk = sum(p.risk_score for p in members) / len(members)
        growth = self._growth_ratio(members, first, last)
        radius = bounding_radius_km(coords)

        severity = self._severity(
            reports=len(members), animals=animals, deaths=deaths,
            mean_risk=mean_risk, growth=growth, villages=len(villages),
        )

        return Cluster(
            cluster_id=cluster_id,
            point_ids=[p.report_id for p in members],
            centroid_lat=clat,
            centroid_lon=clon,
            radius_km=radius,
            first_seen=first,
            last_seen=last,
            report_count=len(members),
            animal_count=animals,
            death_count=deaths,
            villages=villages,
            species=species,
            dominant_syndrome=dominant,
            syndrome_profile=dict(sorted(syndrome_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            top_symptoms=top_symptoms,
            mean_risk_score=mean_risk,
            severity_score=severity,
            growth_ratio=growth,
            explanation=self._explain(
                members, dominant, top_symptoms, villages, radius, growth, deaths,
            ),
        )

    @staticmethod
    def _growth_ratio(members: list[ClusterPoint], first: datetime, last: datetime) -> float:
        """Reports in the final quarter of the span vs the mean of the earlier ones.

        Above 1.0 means the event is still accelerating -- which is the part a
        responder cares about far more than the raw total.
        """
        span = (last - first).total_seconds()
        if span <= 0:
            return 1.0
        cutoff = last - timedelta(seconds=span * 0.25)
        recent = sum(1 for p in members if p.observed_at >= cutoff)
        earlier = len(members) - recent
        if earlier == 0:
            return float(len(members))
        # Compare like with like: recent covers a quarter of the span.
        return (recent / 0.25) / (earlier / 0.75) if earlier else float(recent)

    @staticmethod
    def _severity(
        *, reports: int, animals: int, deaths: int,
        mean_risk: float, growth: float, villages: int,
    ) -> float:
        size = min(30.0, 7.0 * (reports ** 0.6))
        impact = min(15.0, 1.6 * animals)
        mortality = min(25.0, 9.0 * deaths)
        clinical = min(20.0, mean_risk * 0.25)
        momentum = min(10.0, max(0.0, (growth - 1.0) * 6.0))
        spread = min(10.0, 3.5 * max(0, villages - 1))
        return min(100.0, size + impact + mortality + clinical + momentum + spread)

    @staticmethod
    def _explain(
        members: list[ClusterPoint],
        dominant: str | None,
        top_symptoms: list[tuple[str, int]],
        villages: list[str],
        radius: float,
        growth: float,
        deaths: int,
    ) -> str:
        signs = ", ".join(taxonomy.label_for(code).lower() for code, _ in top_symptoms[:3])
        syndrome = taxonomy.SYNDROME_LABELS.get(dominant or "", "mixed").lower()
        where = (
            f"{len(villages)} villages" if len(villages) > 1
            else (villages[0] if villages else "a single locality")
        )
        trend = (
            "still accelerating" if growth > 1.3
            else "stable" if growth > 0.7 else "declining"
        )
        parts = [
            f"{len(members)} reports within {radius:.1f} km of each other in {where} "
            f"share a {syndrome} presentation",
            f"most frequent signs are {signs}" if signs else "",
            f"reporting rate is {trend}",
        ]
        if deaths:
            parts.append(f"{deaths} death(s) recorded inside the cluster")
        return ". ".join(p for p in parts if p) + "."


def detect_clusters(
    points: Sequence[ClusterPoint], config: ClusterConfig | None = None
) -> list[Cluster]:
    return GeoTemporalClusterDetector(config).detect(points)
