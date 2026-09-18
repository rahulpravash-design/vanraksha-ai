"""Dashboard aggregations and the grounded assistant endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from vanraksha_ai.assistant import AssistantContext, HealthAssistant

from ..db import get_db
from ..models import Cluster, ClusterStatus, User
from ..schemas import AssistantAnswer, AssistantQuery, ScopeSummary
from ..security import get_current_user, require_staff
from ..services.analytics import (
    response_performance,
    scope_summary,
    vaccination_coverage,
    village_breakdown,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

#: No language model is wired in by default. The assistant then answers from
#: deterministic templates over the same context, which is a degradation in
#: fluency only -- see services/ai-engine/vanraksha_ai/assistant/agent.py.
_assistant = HealthAssistant(model=None)


@router.get("/summary", response_model=ScopeSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    return scope_summary(db, user, days=days)


@router.get("/villages", response_model=list[dict])
def villages(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    return village_breakdown(db, user, days=days)


@router.get("/performance", response_model=dict)
def performance(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    days: int = Query(default=90, ge=7, le=365),
) -> dict:
    """Operational KPIs measured from recorded timestamps, not self-report."""
    return response_performance(db, user, days=days)


@router.get("/vaccination-coverage", response_model=dict)
def coverage(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return vaccination_coverage(db, user)


@router.post("/assistant", response_model=AssistantAnswer)
def ask_assistant(
    payload: AssistantQuery,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantAnswer:
    """Answer a question about the records this user may see.

    The context handed to the assistant is built from the caller's own scoped
    aggregates, so it cannot describe data the caller is not entitled to. Two
    guardrails then apply regardless of how the answer was produced: diagnosis
    and prescription requests are redirected, and any generated text containing
    a dose is replaced.
    """
    summary_data = scope_summary(db, user, days=payload.days)

    active = db.scalars(
        select(Cluster).where(
            Cluster.status.in_([ClusterStatus.ACTIVE, ClusterStatus.UNDER_INVESTIGATION])
        )
    ).all()
    visible_names = {row["name"] for row in village_breakdown(db, user, days=payload.days)}
    scoped_clusters = [
        {
            "cluster_id": c.signature[:8],
            "report_count": c.report_count,
            "severity_score": round(c.severity_score, 1),
            "dominant_syndrome": c.dominant_syndrome,
        }
        for c in active
        if not visible_names or set(c.villages or []) & visible_names
    ]

    context = AssistantContext(
        scope_label=summary_data["scope"],
        period_label=f"the last {payload.days} days",
        report_count=summary_data["report_count"],
        previous_period_count=summary_data["previous_period_count"],
        animal_count=summary_data["animal_count"],
        death_count=summary_data["death_count"],
        syndrome_counts=summary_data["syndrome_counts"],
        top_symptoms=[(row["code"], row["count"]) for row in summary_data["top_symptoms"]],
        band_counts=summary_data["band_counts"],
        active_clusters=scoped_clusters,
        open_cases=summary_data["open_cases"],
        overdue_vaccinations=summary_data["overdue_vaccinations"],
        weekly_series=[point["count"] for point in summary_data["weekly_series"]],
    )

    result = _assistant.answer(payload.question, context)
    return AssistantAnswer(
        answer=result["answer"],
        source=result["source"],
        grounded_in=result["grounded_in"],
        guardrail=result.get("guardrail"),
        assistant_version=result["assistant_version"],
    )
