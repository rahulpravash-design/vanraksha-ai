"""Turning a stored report into an assessment and, when warranted, a case.

This is the join between the persistence layer and the engine. The engine knows
nothing about the database; this module does the mapping in both directions and
owns the side effects -- writing the assessment, opening a case, and recording
an audit entry.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vanraksha_ai.models import Observation, RiskBand, VaccinationStatus
from vanraksha_ai.risk import RiskEngine
from vanraksha_ai.taxonomy import normalise

from ..models import (
    Animal,
    Case,
    CaseStatus,
    Cluster,
    ClusterStatus,
    HealthReport,
    RiskAssessmentRecord,
    Vaccination,
    utcnow,
)

_engine = RiskEngine()

#: Bands at which a veterinary case is opened automatically. Below this the
#: report is recorded and monitored -- opening a case for every routine report
#: would bury the queue that the escalated ones depend on.
CASE_OPENING_BANDS = {RiskBand.PRIORITY, RiskBand.URGENT, RiskBand.EMERGENCY}


def vaccination_status_for(db: Session, animal_id: str | None) -> VaccinationStatus:
    """Derive vaccination standing from the animal's own record."""
    if not animal_id:
        return VaccinationStatus.UNKNOWN

    rows = db.scalars(
        select(Vaccination).where(Vaccination.animal_id == animal_id)
    ).all()
    if not rows:
        return VaccinationStatus.NEVER

    now = utcnow()
    due_dates = [r.next_due_on for r in rows if r.next_due_on]
    if not due_dates:
        return VaccinationStatus.UNKNOWN
    # Overdue if any scheduled booster has passed its due date.
    return (
        VaccinationStatus.OVERDUE
        if any(due < now for due in due_dates)
        else VaccinationStatus.UP_TO_DATE
    )


def prior_report_count(db: Session, animal_id: str | None, before, days: int = 14) -> int:
    if not animal_id:
        return 0
    since = before - timedelta(days=days)
    return int(
        db.scalar(
            select(func.count(HealthReport.id)).where(
                HealthReport.animal_id == animal_id,
                HealthReport.reported_at >= since,
                HealthReport.reported_at < before,
            )
        )
        or 0
    )


def inside_active_cluster(db: Session, report: HealthReport) -> bool:
    """Whether this report is already part of a live cluster.

    Checked by membership rather than by recomputing geometry, so triage stays
    consistent with whatever the last surveillance sweep concluded.
    """
    if not report.id:
        return False
    active = db.scalars(
        select(Cluster).where(
            Cluster.status.in_([ClusterStatus.ACTIVE, ClusterStatus.UNDER_INVESTIGATION])
        )
    ).all()
    return any(report.id in (c.report_ids or []) for c in active)


def build_observation(db: Session, report: HealthReport) -> Observation:
    """Map a stored report onto the engine's input type."""
    animal: Animal | None = db.get(Animal, report.animal_id) if report.animal_id else None

    symptoms = list(report.symptom_codes or [])
    if report.symptoms_text:
        symptoms.append(report.symptoms_text)

    return Observation(
        report_id=report.id,
        species=report.species,
        reported_at=report.reported_at,
        symptoms=symptoms,
        animal_id=report.animal_id,
        farm_id=report.farm_id,
        village_id=report.village_id,
        latitude=report.latitude,
        longitude=report.longitude,
        age_months=animal.age_months if animal else None,
        sex=animal.sex if animal else None,
        pregnant=bool(animal and animal.is_pregnant),
        lactating=bool(animal and animal.is_lactating),
        temperature_c=report.temperature_c,
        duration_hours=report.duration_hours,
        herd_size=report.herd_size,
        affected_count=report.affected_count,
        deaths_count=report.deaths_count,
        vaccination_status=vaccination_status_for(db, report.animal_id),
        prior_reports_14d=prior_report_count(db, report.animal_id, report.reported_at),
        in_active_cluster=inside_active_cluster(db, report),
        notes=report.notes or "",
    )


def assess_report(db: Session, report: HealthReport) -> RiskAssessmentRecord:
    """Score a report, persist the verdict, and open a case if it warrants one.

    Safe to call again for the same report: the existing assessment is replaced
    rather than duplicated, which is what makes re-running a tuned engine over
    history possible.
    """
    observation = build_observation(db, report)
    result = _engine.assess(observation)

    # Backfill the normalised codes so that clustering and analytics read from
    # the report row without re-parsing free text every time.
    normalised = normalise(observation.symptoms)
    report.symptom_codes = normalised.codes

    # Unmatched phrases are a property of what the reporter originally wrote,
    # and they are the signal that the taxonomy needs a new synonym. A
    # re-assessment sees only the already-normalised codes, so replacing the
    # list here would silently erase them -- they are merged instead.
    unmatched = list(report.unmatched_terms or [])
    for term in normalised.unmatched:
        if term not in unmatched:
            unmatched.append(term)
    report.unmatched_terms = unmatched

    existing = db.scalar(
        select(RiskAssessmentRecord).where(RiskAssessmentRecord.report_id == report.id)
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    record = RiskAssessmentRecord(
        report_id=report.id,
        score=result.score,
        band=result.band.value,
        contributions=[c.to_dict() for c in result.contributions],
        syndromes=result.syndromes,
        dominant_syndrome=result.dominant_syndrome,
        cautions=[c.to_dict() for c in result.cautions],
        recommended_action=result.recommended_action,
        response_target_hours=result.response_target_hours,
        completeness=result.completeness,
        engine_version=result.engine_version,
    )
    db.add(record)
    db.flush()

    _sync_case(db, report, result.band, result.response_target_hours)
    return record


def _sync_case(db: Session, report: HealthReport, band: RiskBand, target_hours: int) -> None:
    """Open, or re-prioritise, the veterinary case for this report."""
    case = db.scalar(select(Case).where(Case.report_id == report.id))

    if band not in CASE_OPENING_BANDS:
        return

    # A case opens when the system learns about the report, not when the sweep
    # happens to run. Using the wall clock here would stamp every case in a
    # backfill with the same instant and make response-time analytics -- which
    # are measured as (assigned_at - opened_at) -- meaningless.
    opened_at = report.received_at or report.reported_at or utcnow()
    due = report.reported_at + timedelta(hours=target_hours)

    if case is None:
        db.add(
            Case(
                report_id=report.id,
                band=band.value,
                status=CaseStatus.OPEN,
                opened_at=opened_at,
                due_at=due,
            )
        )
        db.flush()
        return

    # A re-assessment that raises the band must pull the deadline in; one that
    # lowers it must not silently extend a deadline a vet is already working to.
    if RiskBand(case.band).rank < band.rank:
        case.band = band.value
        case.due_at = due
