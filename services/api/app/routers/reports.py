"""Field reporting: the entry point the whole platform exists to serve."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vanraksha_ai.taxonomy import BY_CODE, SYNDROME_LABELS, normalise

from ..audit import record
from ..db import get_db
from ..models import Animal, Farm, HealthReport, Role, User, utcnow
from ..schemas import HealthReportCreate, HealthReportOut, SyncBatch, SyncItemResult, SyncResult
from ..security import can_read_report, get_current_user
from ..services.analytics import apply_scope, scope_village_ids
from ..services.triage import assess_report

router = APIRouter(prefix="/reports", tags=["reports"])


def _resolve_context(db: Session, payload: HealthReportCreate, user: User) -> dict:
    """Fill in farm, village and herd size from the animal where the client
    could not, and check the reporter is entitled to report on this animal."""
    context: dict = {
        "farm_id": payload.farm_id,
        "village_id": payload.village_id,
        "herd_size": payload.herd_size,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }

    if payload.animal_id:
        animal = db.get(Animal, payload.animal_id)
        if animal is None:
            raise HTTPException(status_code=404, detail="Animal not found.")
        farm = db.get(Farm, animal.farm_id)
        if farm is None:
            raise HTTPException(status_code=404, detail="Animal's farm not found.")
        if user.role is Role.FARMER and farm.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only report on animals in your own farms.",
            )
        context["farm_id"] = context["farm_id"] or farm.id
        context["village_id"] = context["village_id"] or farm.village_id
        context["herd_size"] = context["herd_size"] or farm.herd_size
        if context["latitude"] is None:
            context["latitude"], context["longitude"] = farm.latitude, farm.longitude

    elif payload.farm_id:
        farm = db.get(Farm, payload.farm_id)
        if farm is None:
            raise HTTPException(status_code=404, detail="Farm not found.")
        if user.role is Role.FARMER and farm.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only report on your own farms.",
            )
        context["village_id"] = context["village_id"] or farm.village_id
        context["herd_size"] = context["herd_size"] or farm.herd_size
        if context["latitude"] is None:
            context["latitude"], context["longitude"] = farm.latitude, farm.longitude

    return context


def _persist(db: Session, payload: HealthReportCreate, user: User) -> HealthReport:
    context = _resolve_context(db, payload, user)
    normalised = normalise(list(payload.symptoms) + ([payload.symptoms_text] if payload.symptoms_text else []))

    report = HealthReport(
        client_uuid=payload.client_uuid,
        animal_id=payload.animal_id,
        farm_id=context["farm_id"],
        village_id=context["village_id"],
        reporter_id=user.id,
        species=payload.species,
        reported_at=payload.reported_at or utcnow(),
        symptoms_text=payload.symptoms_text,
        symptom_codes=normalised.codes,
        unmatched_terms=normalised.unmatched,
        temperature_c=payload.temperature_c,
        duration_hours=payload.duration_hours,
        affected_count=payload.affected_count,
        deaths_count=payload.deaths_count,
        herd_size=context["herd_size"],
        latitude=context["latitude"],
        longitude=context["longitude"],
        notes=payload.notes,
        submitted_offline=payload.submitted_offline,
    )
    db.add(report)
    db.flush()
    assess_report(db, report)
    return report


@router.post("", response_model=HealthReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: HealthReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HealthReport:
    """File a report and get the triage verdict back in the same response.

    Returning the assessment immediately is what lets the field app tell a
    farmer "this needs a vet today" before they walk away from the animal.
    """
    existing = db.scalar(
        select(HealthReport).where(HealthReport.client_uuid == payload.client_uuid)
    )
    if existing is not None:
        # Idempotent replay of a queued submission, not a new report.
        return existing

    report = _persist(db, payload, user)
    record(db, user, "report.create", entity_type="report", entity_id=report.id,
           detail={"band": report.assessment.band if report.assessment else None})
    db.commit()
    db.refresh(report)
    return report


@router.post("/sync", response_model=SyncResult)
def sync_offline_batch(
    batch: SyncBatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SyncResult:
    """Drain a device's offline queue.

    Each item is settled independently: one malformed report in a batch of
    forty must not cost the farmer the other thirty-nine. Duplicates are
    reported as such rather than failing, because a client that retries after a
    timeout genuinely does not know whether the first attempt landed.
    """
    results: list[SyncItemResult] = []
    accepted = duplicates = rejected = 0

    for item in batch.reports:
        existing = db.scalar(
            select(HealthReport).where(HealthReport.client_uuid == item.client_uuid)
        )
        if existing is not None:
            duplicates += 1
            results.append(
                SyncItemResult(
                    client_uuid=item.client_uuid,
                    status="duplicate",
                    report_id=existing.id,
                    band=existing.assessment.band if existing.assessment else None,
                    detail="Already received; the queued copy can be discarded.",
                )
            )
            continue

        try:
            item.submitted_offline = True
            report = _persist(db, item, user)
            db.flush()
            accepted += 1
            results.append(
                SyncItemResult(
                    client_uuid=item.client_uuid,
                    status="accepted",
                    report_id=report.id,
                    band=report.assessment.band if report.assessment else None,
                )
            )
        except HTTPException as exc:
            db.rollback()
            rejected += 1
            results.append(
                SyncItemResult(
                    client_uuid=item.client_uuid, status="rejected", detail=str(exc.detail)
                )
            )

    record(db, user, "report.sync", detail={
        "accepted": accepted, "duplicates": duplicates, "rejected": rejected,
        "device_id": batch.device_id,
    })
    db.commit()

    return SyncResult(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        results=results,
        server_time=utcnow(),
    )


@router.get("", response_model=list[HealthReportOut])
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365),
    band: str | None = Query(default=None),
    village_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[HealthReport]:
    since = utcnow() - timedelta(days=days)
    stmt = select(HealthReport).where(HealthReport.reported_at >= since)
    stmt = apply_scope(stmt, user, scope_village_ids(db, user))

    if village_id:
        stmt = stmt.where(HealthReport.village_id == village_id)

    rows = db.scalars(
        stmt.order_by(HealthReport.reported_at.desc()).limit(limit).offset(offset)
    ).all()

    if band:
        rows = [r for r in rows if r.assessment and r.assessment.band == band]
    return list(rows)


@router.get("/taxonomy", response_model=dict)
def taxonomy_reference() -> dict:
    """The controlled vocabulary, for building field-app symptom pickers.

    Served from the engine so the app and the scorer can never drift apart.
    """
    return {
        "syndromes": [
            {"code": code, "label": label} for code, label in SYNDROME_LABELS.items()
        ],
        "symptoms": [
            {
                "code": term.code,
                "label": term.label,
                "syndromes": list(term.syndromes),
                "severity_weight": term.severity_weight,
                "synonyms": list(term.synonyms),
            }
            for term in BY_CODE.values()
        ],
    }


@router.get("/{report_id}", response_model=HealthReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HealthReport:
    report = db.get(HealthReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    block = None
    if report.village_id:
        from ..models import Village

        village = db.get(Village, report.village_id)
        block = village.block if village else None

    if not can_read_report(user, report.reporter_id, block):
        # 404 rather than 403: confirming a record exists is itself a disclosure.
        raise HTTPException(status_code=404, detail="Report not found.")
    return report
