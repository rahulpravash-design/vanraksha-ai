"""Append-only audit trail.

Every state-changing request writes a row. Health records and farmer contact
details attract access that has to be answerable for, and a trail that is
written only when someone remembers to call it is not a trail.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_role=actor.role.value if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
        )
    )
