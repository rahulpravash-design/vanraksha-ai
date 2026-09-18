"""Aggregations for the veterinary and administrative dashboards.

Every figure here is scoped by the caller's permitted geography, applied in the
query rather than after it. Filtering in the presentation layer is not access
control -- it is a data leak with a nicer font.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from vanraksha_ai.trends import bucket_counts, counts_only, describe_trend

from ..models import (
    Animal,
    Case,
    CaseStatus,
    Cluster,
    ClusterStatus,
    Farm,
    HealthReport,
    RiskAssessmentRecord,
    User,
    Vaccination,
    Village,
    utcnow,
)
from ..security import visible_scope


def scope_village_ids(db: Session, user: User) -> list[str] | None:
    """Village ids the user may see; ``None`` means unrestricted."""
    scope = visible_scope(user)

    if scope["level"] == "district":
        if not scope.get("district"):
            return None  # super admin with no district pinned sees everything
        rows = db.scalars(
            select(Village.id).where(Village.district == scope["district"])
        ).all()
        return list(rows)

    if scope["level"] == "block":
        if not scope.get("block"):
            return []
        rows = db.scalars(select(Village.id).where(Village.block == scope["block"])).all()
        return list(rows)

    # A farmer sees only their own farms' villages.
    rows = db.scalars(
        select(Farm.village_id).where(Farm.owner_id == user.id).distinct()
    ).all()
    return list(rows)


def apply_scope(stmt: Select, user: User, village_ids: list[str] | None) -> Select:
    """Restrict a report query to the caller's permitted geography."""
    if village_ids is None:
        return stmt
    if not village_ids:
        # An empty permitted set must return nothing, not everything.
        return stmt.where(HealthReport.village_id.is_(None) & (HealthReport.id == ""))
    scoped = stmt.where(HealthReport.village_id.in_(village_ids))
    if visible_scope(user)["level"] == "own":
        scoped = scoped.where(HealthReport.reporter_id == user.id)
    return scoped


def scope_summary(
    db: Session, user: User, *, days: int = 30, now: datetime | None = None
) -> dict:
    """The headline figures for whatever geography this user is entitled to."""
    now = now or utcnow()
    since = now - timedelta(days=days)
    previous_since = since - timedelta(days=days)

    village_ids = scope_village_ids(db, user)
    scope_label = _scope_label(db, user, village_ids)

    reports = db.scalars(
        apply_scope(
            select(HealthReport).where(HealthReport.reported_at >= since), user, village_ids
        )
    ).all()
    previous_count = len(
        db.scalars(
            apply_scope(
                select(HealthReport).where(
                    HealthReport.reported_at >= previous_since,
                    HealthReport.reported_at < since,
                ),
                user,
                village_ids,
            )
        ).all()
    )

    band_counts: dict[str, int] = {}
    syndrome_counts: dict[str, int] = {}
    symptom_counts: dict[str, int] = {}
    animals = deaths = 0

    for report in reports:
        animals += report.affected_count
        deaths += report.deaths_count
        for code in report.symptom_codes or []:
            symptom_counts[code] = symptom_counts.get(code, 0) + 1
        assessment = report.assessment
        if assessment:
            band_counts[assessment.band] = band_counts.get(assessment.band, 0) + 1
            for syndrome in assessment.syndromes or []:
                syndrome_counts[syndrome] = syndrome_counts.get(syndrome, 0) + 1

    report_ids = [r.id for r in reports]
    open_cases = overdue_cases = 0
    if report_ids:
        cases = db.scalars(select(Case).where(Case.report_id.in_(report_ids))).all()
        open_cases = sum(
            1 for c in cases if c.status not in (CaseStatus.RESOLVED, CaseStatus.CLOSED)
        )
        overdue_cases = sum(1 for c in cases if c.is_overdue)

    active_clusters = _active_cluster_count(db, village_ids)
    overdue_vaccinations = _overdue_vaccination_count(db, village_ids, now)

    series = bucket_counts(
        [r.reported_at for r in reports],
        period="week",
        periods=max(4, days // 7),
        end=now.date(),
    )
    counts = counts_only(series)

    return {
        "scope": scope_label,
        "period_days": days,
        "report_count": len(reports),
        "previous_period_count": previous_count,
        "animal_count": animals,
        "death_count": deaths,
        "open_cases": open_cases,
        "overdue_cases": overdue_cases,
        "active_clusters": active_clusters,
        "overdue_vaccinations": overdue_vaccinations,
        "band_counts": band_counts,
        "syndrome_counts": dict(
            sorted(syndrome_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "top_symptoms": [
            {"code": code, "count": count}
            for code, count in sorted(symptom_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ],
        "weekly_series": [
            {"period_start": p.period_start.isoformat(), "count": p.count} for p in series
        ],
        "trend": describe_trend(counts),
    }


def village_breakdown(
    db: Session, user: User, *, days: int = 30, now: datetime | None = None
) -> list[dict]:
    """Per-village figures, for the map and the district table."""
    now = now or utcnow()
    since = now - timedelta(days=days)
    village_ids = scope_village_ids(db, user)

    reports = db.scalars(
        apply_scope(
            select(HealthReport).where(HealthReport.reported_at >= since), user, village_ids
        )
    ).all()

    villages = {
        v.id: v
        for v in db.scalars(
            select(Village).where(Village.id.in_(village_ids))
            if village_ids is not None
            else select(Village)
        ).all()
    }

    rows: dict[str, dict] = {}
    for village in villages.values():
        rows[village.id] = {
            "village_id": village.id,
            "name": village.name,
            "block": village.block,
            "district": village.district,
            "latitude": village.latitude,
            "longitude": village.longitude,
            "livestock_population": village.livestock_population,
            "report_count": 0,
            "animal_count": 0,
            "death_count": 0,
            "escalated_count": 0,
        }

    for report in reports:
        row = rows.get(report.village_id or "")
        if row is None:
            continue
        row["report_count"] += 1
        row["animal_count"] += report.affected_count
        row["death_count"] += report.deaths_count
        if report.assessment and report.assessment.band in ("priority", "urgent", "emergency"):
            row["escalated_count"] += 1

    return sorted(rows.values(), key=lambda r: (-r["report_count"], r["name"]))


def response_performance(
    db: Session, user: User, *, days: int = 90, now: datetime | None = None
) -> dict:
    """Operational KPIs: how fast the loop actually closes.

    Reporting latency, triage-to-assignment, and case closure are the measures
    that say whether the platform changed anything. They are computed from
    timestamps the system already records rather than self-reported.
    """
    now = now or utcnow()
    since = now - timedelta(days=days)
    village_ids = scope_village_ids(db, user)

    reports = db.scalars(
        apply_scope(
            select(HealthReport).where(HealthReport.reported_at >= since), user, village_ids
        )
    ).all()
    if not reports:
        return {
            "period_days": days, "reports": 0, "cases": 0,
            "median_reporting_lag_hours": None, "median_assignment_hours": None,
            "median_resolution_hours": None, "sla_met_rate": None,
            "offline_share": None, "data_completeness": None,
        }

    lags = [
        (r.received_at - r.reported_at).total_seconds() / 3600.0
        for r in reports
        if r.received_at and r.reported_at
    ]
    completeness = [
        r.assessment.completeness for r in reports if r.assessment is not None
    ]
    offline = sum(1 for r in reports if r.submitted_offline)

    cases = db.scalars(
        select(Case).where(Case.report_id.in_([r.id for r in reports]))
    ).all()
    assignment = [
        (c.assigned_at - c.opened_at).total_seconds() / 3600.0
        for c in cases
        if c.assigned_at and c.opened_at
    ]
    resolution = [
        (c.closed_at - c.opened_at).total_seconds() / 3600.0
        for c in cases
        if c.closed_at and c.opened_at
    ]
    finished = [c for c in cases if c.closed_at and c.due_at]
    sla_met = sum(1 for c in finished if c.closed_at <= c.due_at)

    return {
        "period_days": days,
        "reports": len(reports),
        "cases": len(cases),
        "median_reporting_lag_hours": _median(lags),
        "median_assignment_hours": _median(assignment),
        "median_resolution_hours": _median(resolution),
        "sla_met_rate": round(sla_met / len(finished), 3) if finished else None,
        "offline_share": round(offline / len(reports), 3),
        "data_completeness": round(sum(completeness) / len(completeness), 3)
        if completeness
        else None,
    }


def vaccination_coverage(db: Session, user: User, *, now: datetime | None = None) -> dict:
    """Share of animals in scope with a vaccination that is not overdue."""
    now = now or utcnow()
    village_ids = scope_village_ids(db, user)

    animal_stmt = select(Animal).join(Farm, Animal.farm_id == Farm.id)
    if village_ids is not None:
        if not village_ids:
            return {"animals": 0, "covered": 0, "overdue": 0, "never": 0, "coverage_rate": None}
        animal_stmt = animal_stmt.where(Farm.village_id.in_(village_ids))
    if visible_scope(user)["level"] == "own":
        animal_stmt = animal_stmt.where(Farm.owner_id == user.id)

    animals = db.scalars(animal_stmt).all()
    if not animals:
        return {"animals": 0, "covered": 0, "overdue": 0, "never": 0, "coverage_rate": None}

    animal_ids = [a.id for a in animals]
    rows = db.execute(
        select(Vaccination.animal_id, func.max(Vaccination.next_due_on))
        .where(Vaccination.animal_id.in_(animal_ids))
        .group_by(Vaccination.animal_id)
    ).all()
    latest = {animal_id: due for animal_id, due in rows}

    covered = sum(1 for a in animals if latest.get(a.id) and latest[a.id] >= now)
    overdue = sum(1 for a in animals if latest.get(a.id) and latest[a.id] < now)
    never = len(animals) - covered - overdue

    return {
        "animals": len(animals),
        "covered": covered,
        "overdue": overdue,
        "never": never,
        "coverage_rate": round(covered / len(animals), 3),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    value = (
        ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    )
    return round(value, 2)


def _active_cluster_count(db: Session, village_ids: list[str] | None) -> int:
    clusters = db.scalars(
        select(Cluster).where(
            Cluster.status.in_([ClusterStatus.ACTIVE, ClusterStatus.UNDER_INVESTIGATION])
        )
    ).all()
    if village_ids is None:
        return len(clusters)
    if not village_ids:
        return 0
    names = {
        v.name
        for v in db.scalars(select(Village).where(Village.id.in_(village_ids))).all()
    }
    return sum(1 for c in clusters if set(c.villages or []) & names)


def _overdue_vaccination_count(
    db: Session, village_ids: list[str] | None, now: datetime
) -> int:
    stmt = (
        select(func.count(func.distinct(Vaccination.animal_id)))
        .select_from(Vaccination)
        .join(Animal, Vaccination.animal_id == Animal.id)
        .join(Farm, Animal.farm_id == Farm.id)
        .where(Vaccination.next_due_on.is_not(None), Vaccination.next_due_on < now)
    )
    if village_ids is not None:
        if not village_ids:
            return 0
        stmt = stmt.where(Farm.village_id.in_(village_ids))
    return int(db.scalar(stmt) or 0)


def _scope_label(db: Session, user: User, village_ids: list[str] | None) -> str:
    scope = visible_scope(user)
    if scope["level"] == "district":
        return f"{scope.get('district') or 'All'} district"
    if scope["level"] == "block":
        return f"{scope.get('block') or 'Unassigned'} block"
    return f"{user.full_name}'s farms"
