"""The surveillance sweep: clustering, aberration detection, and alert routing.

Run on demand from the API and on a schedule in deployment. Everything it
writes is idempotent, so running it twice in a row changes nothing — which
matters because the alternative is a duplicate alert storm on a retry.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from vanraksha_ai.clustering import ClusterConfig, ClusterPoint, GeoTemporalClusterDetector
from vanraksha_ai.models import SPECIES_GROUP

from ..config import get_settings
from ..models import Alert, Case, Cluster, ClusterStatus, HealthReport, Village, utcnow

settings = get_settings()


def _cluster_config() -> ClusterConfig:
    return ClusterConfig(
        radius_km=settings.cluster_radius_km,
        window_hours=settings.cluster_window_hours,
        min_reports=settings.cluster_min_reports,
    )


def _signature(report_ids: list[str]) -> str:
    """Stable identity for a cluster, derived from its members.

    A cluster that gains a report between sweeps is the same event and must
    update in place. Hashing the sorted member list gives that for free, at the
    cost of treating a membership change as a new cluster -- which is the right
    trade, because a materially different member set *is* a different event.
    """
    joined = "|".join(sorted(report_ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _load_points(db: Session, since: datetime) -> list[ClusterPoint]:
    reports = db.scalars(
        select(HealthReport).where(
            HealthReport.reported_at >= since,
            HealthReport.latitude.is_not(None),
            HealthReport.longitude.is_not(None),
        )
    ).all()

    # The detector writes the locality straight into its explanation, so it is
    # given the village *name*. Handing it an identifier produces a sentence
    # like "9 reports in 1b290a92-5044-..." -- technically accurate and useless
    # to the officer who has to act on it.
    village_names = {v.id: v.name for v in db.scalars(select(Village)).all()}

    points: list[ClusterPoint] = []
    for report in reports:
        assessment = report.assessment
        points.append(
            ClusterPoint(
                report_id=report.id,
                latitude=float(report.latitude),
                longitude=float(report.longitude),
                observed_at=report.reported_at,
                symptom_codes=list(report.symptom_codes or []),
                species=report.species,
                species_group=SPECIES_GROUP.get(report.species, report.species),
                village_id=village_names.get(report.village_id or "", report.village_id),
                animal_id=report.animal_id,
                affected_count=report.affected_count,
                deaths_count=report.deaths_count,
                risk_score=assessment.score if assessment else 0.0,
            )
        )
    return points


def run_sweep(db: Session, *, window_days: int = 21, now: datetime | None = None) -> dict:
    """Detect clusters over a trailing window and raise the alerts they justify."""
    now = now or utcnow()
    since = now - timedelta(days=window_days)

    points = _load_points(db, since)
    detector = GeoTemporalClusterDetector(_cluster_config())
    detected = detector.detect(points)

    seen_signatures: set[str] = set()

    for cluster in detected:
        signature = _signature(cluster.point_ids)
        seen_signatures.add(signature)

        existing = db.scalar(select(Cluster).where(Cluster.signature == signature))
        if existing is None:
            existing = Cluster(signature=signature, detected_at=now)
            db.add(existing)

        # A cluster a reviewer already dismissed stays dismissed; re-raising it
        # every sweep is how a surveillance system trains its users to ignore it.
        if existing.status is not ClusterStatus.DISMISSED:
            existing.status = existing.status or ClusterStatus.ACTIVE

        existing.centroid_lat = cluster.centroid_lat
        existing.centroid_lon = cluster.centroid_lon
        existing.radius_km = cluster.radius_km
        existing.first_seen = cluster.first_seen
        existing.last_seen = cluster.last_seen
        existing.report_count = cluster.report_count
        existing.animal_count = cluster.animal_count
        existing.death_count = cluster.death_count
        existing.severity_score = cluster.severity_score
        existing.growth_ratio = cluster.growth_ratio
        existing.dominant_syndrome = cluster.dominant_syndrome
        existing.villages = cluster.villages
        existing.species = cluster.species
        existing.report_ids = cluster.point_ids
        existing.top_symptoms = [{"code": c, "count": n} for c, n in cluster.top_symptoms]
        existing.explanation = cluster.explanation
        existing.detector_version = cluster.detector_version
        db.flush()

        _link_cases(db, existing)
        if existing.status is not ClusterStatus.DISMISSED:
            _raise_cluster_alert(db, existing, now)

    _retire_stale_clusters(db, seen_signatures, now)
    db.commit()

    return {
        "swept_at": now.isoformat(),
        "window_days": window_days,
        "reports_considered": len(points),
        "clusters_detected": len(detected),
        "clusters": [c.to_dict() for c in detected],
    }


def _link_cases(db: Session, cluster: Cluster) -> None:
    """Attach the cases belonging to this cluster's reports, so a vet opening
    one case can see it is part of a larger event."""
    if not cluster.report_ids:
        return
    cases = db.scalars(select(Case).where(Case.report_id.in_(cluster.report_ids))).all()
    for case in cases:
        case.cluster_id = cluster.id


def _raise_cluster_alert(db: Session, cluster: Cluster, now: datetime) -> None:
    """Create or refresh the alert for a cluster.

    The dedupe key is the cluster signature, so a sweep that re-detects the same
    cluster updates one alert instead of adding another to the queue.
    """
    dedupe_key = f"cluster:{cluster.signature}"
    alert = db.scalar(select(Alert).where(Alert.dedupe_key == dedupe_key))

    audiences = ["veterinarian", "block_admin"]
    if cluster.severity_score >= 55:
        audiences.append("district_admin")

    title = (
        f"{(cluster.dominant_syndrome or 'mixed').replace('_', ' ').title()} cluster: "
        f"{cluster.report_count} reports"
    )
    scope = ", ".join(cluster.villages) if cluster.villages else "unnamed locality"

    if alert is None:
        db.add(
            Alert(
                dedupe_key=dedupe_key,
                kind="cluster",
                severity=cluster.severity_score,
                title=title,
                body=cluster.explanation,
                scope=scope,
                audiences=audiences,
                evidence={
                    "cluster_id": cluster.id,
                    "signature": cluster.signature,
                    "report_ids": cluster.report_ids,
                    "growth_ratio": round(cluster.growth_ratio, 2),
                    "deaths": cluster.death_count,
                },
                raised_at=now,
            )
        )
        return

    alert.severity = cluster.severity_score
    alert.title = title
    alert.body = cluster.explanation
    alert.audiences = audiences
    alert.evidence = {
        **(alert.evidence or {}),
        "report_ids": cluster.report_ids,
        "growth_ratio": round(cluster.growth_ratio, 2),
        "deaths": cluster.death_count,
    }
    # An escalating cluster is re-surfaced to anyone who already dismissed it.
    if cluster.severity_score >= 70 and alert.acknowledged_at is not None:
        alert.acknowledged_at = None
        alert.acknowledged_by = None


def _retire_stale_clusters(db: Session, live: set[str], now: datetime) -> None:
    """Close out clusters that this sweep no longer detects."""
    stale = db.scalars(
        select(Cluster).where(
            Cluster.status.in_([ClusterStatus.ACTIVE, ClusterStatus.UNDER_INVESTIGATION]),
            Cluster.signature.not_in(live) if live else Cluster.signature.is_not(None),
        )
    ).all()
    for cluster in stale:
        # Only retire once reporting has genuinely stopped, not on the first
        # sweep where the membership shifted.
        if (now - cluster.last_seen) > timedelta(days=14):
            cluster.status = ClusterStatus.RESOLVED
