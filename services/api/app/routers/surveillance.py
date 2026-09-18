"""Clusters, alerts, and the sweep that produces them."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..db import get_db
from ..models import Alert, Cluster, ClusterStatus, User, utcnow
from ..schemas import AlertOut, ClusterOut, ClusterReview
from ..security import get_current_user, require_admin, require_staff
from ..services.surveillance import run_sweep

router = APIRouter(tags=["surveillance"])


@router.post("/surveillance/sweep", response_model=dict)
def sweep(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    window_days: int = Query(default=21, ge=1, le=120),
) -> dict:
    """Re-run cluster detection over a trailing window.

    Idempotent: a cluster already known is updated rather than duplicated, and
    one a reviewer dismissed stays dismissed.
    """
    result = run_sweep(db, window_days=window_days)
    record(db, user, "surveillance.sweep", detail={
        "window_days": window_days, "clusters": result["clusters_detected"]
    })
    db.commit()
    return result


@router.get("/clusters", response_model=list[ClusterOut])
def list_clusters(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    status_filter: ClusterStatus | None = Query(default=None, alias="status"),
    days: int = Query(default=30, ge=1, le=365),
) -> list[Cluster]:
    stmt = select(Cluster).where(Cluster.last_seen >= utcnow() - timedelta(days=days))
    if status_filter:
        stmt = stmt.where(Cluster.status == status_filter)
    return list(db.scalars(stmt.order_by(Cluster.severity_score.desc())).all())


@router.get("/clusters/{cluster_id}", response_model=ClusterOut)
def get_cluster(
    cluster_id: str, db: Session = Depends(get_db), user: User = Depends(require_staff)
) -> Cluster:
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found.")
    return cluster


@router.post("/clusters/{cluster_id}/review", response_model=ClusterOut)
def review_cluster(
    cluster_id: str,
    payload: ClusterReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> Cluster:
    """Record a reviewer's verdict on a cluster.

    This is the ground truth that alert precision is measured against. Without
    it there is no way to tell whether the detector is earning its keep, so the
    review step is part of the product rather than an afterthought.
    """
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found.")

    cluster.review_outcome = payload.outcome
    cluster.review_notes = payload.notes
    cluster.reviewed_by = user.id
    cluster.reviewed_at = utcnow()
    cluster.status = ClusterStatus(payload.outcome)

    record(db, user, "cluster.review", entity_type="cluster", entity_id=cluster.id,
           detail={"outcome": payload.outcome})
    db.commit()
    db.refresh(cluster)
    return cluster


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    unacknowledged_only: bool = Query(default=False),
    days: int = Query(default=14, ge=1, le=180),
) -> list[Alert]:
    """Alerts addressed to this user's role."""
    stmt = select(Alert).where(Alert.raised_at >= utcnow() - timedelta(days=days))
    if unacknowledged_only:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))

    rows = db.scalars(stmt.order_by(Alert.severity.desc(), Alert.raised_at.desc())).all()
    return [a for a in rows if user.role.value in (a.audiences or [])]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if user.role.value not in (alert.audiences or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This alert is not addressed to your role.",
        )

    alert.acknowledged_by = user.id
    alert.acknowledged_at = utcnow()
    record(db, user, "alert.acknowledge", entity_type="alert", entity_id=alert.id)
    db.commit()
    db.refresh(alert)
    return alert
