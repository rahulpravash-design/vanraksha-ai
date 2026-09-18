"""Relational model for the platform.

Shape notes that matter:

* **Reports are immutable facts, assessments are derived.** A `HealthReport` is
  what the farmer said; a `RiskAssessment` is what the engine made of it. They
  are separate tables so that re-running a tuned engine over history never
  rewrites what somebody actually reported.
* **Offline sync needs a client-generated key.** `HealthReport.client_uuid` is
  minted on the device, so replaying a queued submission after a flaky network
  is idempotent instead of creating duplicates.
* **Location is denormalised onto the report.** Farms move, animals are sold,
  village boundaries get redrawn; where the report was filed must not change
  retroactively, because cluster history depends on it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, enum.Enum):
    FARMER = "farmer"
    FIELD_WORKER = "field_worker"
    VETERINARIAN = "veterinarian"
    LAB = "lab"
    BLOCK_ADMIN = "block_admin"
    DISTRICT_ADMIN = "district_admin"
    SUPER_ADMIN = "super_admin"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    AWAITING_LAB = "awaiting_lab"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ClusterStatus(str, enum.Enum):
    ACTIVE = "active"
    UNDER_INVESTIGATION = "under_investigation"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class AnimalStatus(str, enum.Enum):
    ACTIVE = "active"
    SOLD = "sold"
    DECEASED = "deceased"


# ---------------------------------------------------------------------------
# Geography and people
# ---------------------------------------------------------------------------


class Village(Base):
    __tablename__ = "villages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    block: Mapped[str] = mapped_column(String(120), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    livestock_population: Mapped[int] = mapped_column(Integer, default=0)

    farms: Mapped[list["Farm"]] = relationship(back_populates="village")

    __table_args__ = (Index("ix_villages_block_district", "block", "district"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(8), default="en")
    village_id: Mapped[str | None] = mapped_column(ForeignKey("villages.id"))
    block: Mapped[str | None] = mapped_column(String(120), index=True)
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    farms: Mapped[list["Farm"]] = relationship(back_populates="owner")


# ---------------------------------------------------------------------------
# Livestock
# ---------------------------------------------------------------------------


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    village_id: Mapped[str] = mapped_column(ForeignKey("villages.id"), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship(back_populates="farms")
    village: Mapped[Village] = relationship(back_populates="farms")
    animals: Mapped[list["Animal"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan"
    )

    @property
    def herd_size(self) -> int:
        return sum(1 for a in self.animals if a.status == AnimalStatus.ACTIVE)


class Animal(Base):
    __tablename__ = "animals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tag: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    species: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    breed: Mapped[str | None] = mapped_column(String(80))
    sex: Mapped[str | None] = mapped_column(String(16))
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime)
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.id"), nullable=False, index=True)
    status: Mapped[AnimalStatus] = mapped_column(Enum(AnimalStatus), default=AnimalStatus.ACTIVE)
    is_pregnant: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lactating: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="animals")
    reports: Mapped[list["HealthReport"]] = relationship(back_populates="animal")
    vaccinations: Mapped[list["Vaccination"]] = relationship(
        back_populates="animal", cascade="all, delete-orphan"
    )
    treatments: Mapped[list["Treatment"]] = relationship(
        back_populates="animal", cascade="all, delete-orphan"
    )

    # A tag is unique within a farm, not globally -- two farms legitimately
    # number their animals from one.
    __table_args__ = (UniqueConstraint("farm_id", "tag", name="uq_animal_farm_tag"),)

    @property
    def age_months(self) -> int | None:
        if not self.date_of_birth:
            return None
        delta = utcnow() - self.date_of_birth
        return int(delta.days / 30.44)


# ---------------------------------------------------------------------------
# Health events
# ---------------------------------------------------------------------------


class HealthReport(Base):
    __tablename__ = "health_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    #: Minted on the device before the report ever reaches the network. Replaying
    #: a queued submission is therefore idempotent.
    client_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    animal_id: Mapped[str | None] = mapped_column(ForeignKey("animals.id"), index=True)
    farm_id: Mapped[str | None] = mapped_column(ForeignKey("farms.id"), index=True)
    village_id: Mapped[str | None] = mapped_column(ForeignKey("villages.id"), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    species: Mapped[str] = mapped_column(String(32), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    symptoms_text: Mapped[str] = mapped_column(Text, default="")
    symptom_codes: Mapped[list] = mapped_column(JSON, default=list)
    unmatched_terms: Mapped[list] = mapped_column(JSON, default=list)

    temperature_c: Mapped[float | None] = mapped_column(Float)
    duration_hours: Mapped[int | None] = mapped_column(Integer)
    affected_count: Mapped[int] = mapped_column(Integer, default=1)
    deaths_count: Mapped[int] = mapped_column(Integer, default=0)
    herd_size: Mapped[int | None] = mapped_column(Integer)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")

    #: Set when the report arrives from an offline queue rather than live.
    submitted_offline: Mapped[bool] = mapped_column(Boolean, default=False)

    animal: Mapped[Animal | None] = relationship(back_populates="reports")
    assessment: Mapped["RiskAssessmentRecord | None"] = relationship(
        back_populates="report", uselist=False, cascade="all, delete-orphan"
    )
    case: Mapped["Case | None"] = relationship(
        back_populates="report", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_reports_village_time", "village_id", "reported_at"),
        Index("ix_reports_species_time", "species", "reported_at"),
    )


class RiskAssessmentRecord(Base):
    """The engine's verdict on one report, stored with the rules that produced it.

    ``contributions`` and ``engine_version`` are persisted so that an assessment
    made months ago stays explainable even after the rules have been tuned.
    """

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("health_reports.id"), unique=True, nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    contributions: Mapped[list] = mapped_column(JSON, default=list)
    syndromes: Mapped[list] = mapped_column(JSON, default=list)
    dominant_syndrome: Mapped[str | None] = mapped_column(String(32), index=True)
    cautions: Mapped[list] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    response_target_hours: Mapped[int] = mapped_column(Integer, default=168)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)
    engine_version: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    report: Mapped[HealthReport] = relationship(back_populates="assessment")


class Case(Base):
    """A unit of veterinary work opened from a report."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("health_reports.id"), unique=True, nullable=False, index=True
    )
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus), default=CaseStatus.OPEN, index=True
    )
    band: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    assigned_vet_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    outcome: Mapped[str | None] = mapped_column(String(64))
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("clusters.id"), index=True)

    report: Mapped[HealthReport] = relationship(back_populates="case")
    treatments: Mapped[list["Treatment"]] = relationship(back_populates="case")

    @property
    def is_overdue(self) -> bool:
        if self.status in (CaseStatus.RESOLVED, CaseStatus.CLOSED) or not self.due_at:
            return False
        return utcnow() > self.due_at


class Vaccination(Base):
    __tablename__ = "vaccinations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    animal_id: Mapped[str] = mapped_column(ForeignKey("animals.id"), nullable=False, index=True)
    vaccine: Mapped[str] = mapped_column(String(80), nullable=False)
    administered_on: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    next_due_on: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    batch_number: Mapped[str | None] = mapped_column(String(64))
    administered_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    animal: Mapped[Animal] = relationship(back_populates="vaccinations")


class Treatment(Base):
    """A record of what a veterinarian did.

    Written by veterinary staff only. The platform records treatments; it never
    proposes them.
    """

    __tablename__ = "treatments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    animal_id: Mapped[str] = mapped_column(ForeignKey("animals.id"), nullable=False, index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    administered_on: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    administered_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    withdrawal_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    animal: Mapped[Animal] = relationship(back_populates="treatments")
    case: Mapped[Case | None] = relationship(back_populates="treatments")


# ---------------------------------------------------------------------------
# Surveillance
# ---------------------------------------------------------------------------


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    #: Stable key so a cluster that persists between sweeps is updated, not
    #: duplicated. Derived from the cluster's member reports.
    signature: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus), default=ClusterStatus.ACTIVE, index=True
    )
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    animal_count: Mapped[int] = mapped_column(Integer, default=0)
    death_count: Mapped[int] = mapped_column(Integer, default=0)
    severity_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    growth_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    dominant_syndrome: Mapped[str | None] = mapped_column(String(32), index=True)
    villages: Mapped[list] = mapped_column(JSON, default=list)
    species: Mapped[list] = mapped_column(JSON, default=list)
    report_ids: Mapped[list] = mapped_column(JSON, default=list)
    top_symptoms: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    detector_version: Mapped[str] = mapped_column(String(48), default="")

    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Reviewer verdict. This is the ground truth that alert precision is
    #: measured against -- without it there is no way to tune the detector.
    review_outcome: Mapped[str | None] = mapped_column(String(32))
    review_notes: Mapped[str] = mapped_column(Text, default="")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    severity: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(160), default="")
    audiences: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    raised_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    """Append-only record of who did what.

    Health records attract access that needs to be answerable for. Every
    state-changing request writes one row.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(48), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
