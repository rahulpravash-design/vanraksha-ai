"""The veterinary work queue.

Ordering is the product here. A queue sorted by arrival time is the paper
system with extra steps; this one sorts by band, then by how close the case is
to breaching its response target.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vanraksha_ai.models import RiskBand

from ..audit import record
from ..db import get_db
from ..models import Case, CaseStatus, HealthReport, Role, User, Village, utcnow
from ..schemas import CaseAssign, CaseOut, CaseUpdate
from ..security import get_current_user, require_clinical, require_staff

router = APIRouter(prefix="/cases", tags=["cases"])

_BAND_ORDER = {band.value: band.rank for band in RiskBand}


def _serialise(case: Case) -> CaseOut:
    payload = CaseOut.model_validate(case)
    payload.is_overdue = case.is_overdue
    return payload


def _scope_case_ids(db: Session, user: User) -> list[str] | None:
    """Report ids inside this user's geography; ``None`` means unrestricted."""
    if user.role in (Role.SUPER_ADMIN, Role.DISTRICT_ADMIN):
        return None
    if not user.block:
        return []
    village_ids = db.scalars(select(Village.id).where(Village.block == user.block)).all()
    return list(
        db.scalars(
            select(HealthReport.id).where(HealthReport.village_id.in_(list(village_ids)))
        ).all()
    )


@router.get("/queue", response_model=list[CaseOut])
def case_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    mine_only: bool = Query(default=False),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CaseOut]:
    """Open cases, most urgent first.

    Sorted by band, then by remaining time against the response target, so a
    priority case two hours from breaching outranks one logged this minute.
    """
    stmt = select(Case)
    if not include_closed:
        stmt = stmt.where(Case.status.not_in([CaseStatus.RESOLVED, CaseStatus.CLOSED]))
    if mine_only:
        stmt = stmt.where(Case.assigned_vet_id == user.id)

    report_ids = _scope_case_ids(db, user)
    if report_ids is not None:
        if not report_ids:
            return []
        stmt = stmt.where(Case.report_id.in_(report_ids))

    cases = list(db.scalars(stmt).all())
    now = utcnow()
    cases.sort(
        key=lambda c: (
            -_BAND_ORDER.get(c.band, 0),
            (c.due_at - now).total_seconds() if c.due_at else float("inf"),
        )
    )
    return [_serialise(c) for c in cases[:limit]]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: str, db: Session = Depends(get_db), user: User = Depends(require_staff)
) -> CaseOut:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return _serialise(case)


@router.post("/{case_id}/assign", response_model=CaseOut)
def assign_case(
    case_id: str,
    payload: CaseAssign,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> CaseOut:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    vet = db.get(User, payload.veterinarian_id)
    if vet is None or vet.role is not Role.VETERINARIAN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cases can only be assigned to a veterinarian.",
        )
    if not vet.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That veterinarian's account is disabled.",
        )

    case.assigned_vet_id = vet.id
    case.assigned_at = utcnow()
    if case.status is CaseStatus.OPEN:
        case.status = CaseStatus.ASSIGNED

    record(db, user, "case.assign", entity_type="case", entity_id=case.id,
           detail={"veterinarian_id": vet.id})
    db.commit()
    db.refresh(case)
    return _serialise(case)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_clinical),
) -> CaseOut:
    """Advance a case. Clinical roles only."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    changes = payload.model_dump(exclude_unset=True)
    now = utcnow()

    if "status" in changes and changes["status"] is not None:
        new_status = changes["status"]
        if case.status in (CaseStatus.RESOLVED, CaseStatus.CLOSED) and new_status not in (
            CaseStatus.RESOLVED, CaseStatus.CLOSED
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A closed case cannot be reopened; file a new report instead.",
            )
        case.status = new_status
        if case.first_response_at is None and new_status is not CaseStatus.OPEN:
            case.first_response_at = now
        if new_status in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
            case.closed_at = case.closed_at or now

    if changes.get("outcome") is not None:
        case.outcome = changes["outcome"]
    if changes.get("resolution_notes") is not None:
        case.resolution_notes = changes["resolution_notes"]

    record(db, user, "case.update", entity_type="case", entity_id=case.id,
           detail={k: str(v) for k, v in changes.items()})
    db.commit()
    db.refresh(case)
    return _serialise(case)


@router.get("", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    days: int = Query(default=30, ge=1, le=365),
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
) -> list[CaseOut]:
    since = utcnow() - timedelta(days=days)
    stmt = select(Case).where(Case.opened_at >= since)
    if status_filter:
        stmt = stmt.where(Case.status == status_filter)

    report_ids = _scope_case_ids(db, user)
    if report_ids is not None:
        if not report_ids:
            return []
        stmt = stmt.where(Case.report_id.in_(report_ids))

    return [
        _serialise(c) for c in db.scalars(stmt.order_by(Case.opened_at.desc())).all()
    ]
