"""Shared value objects passed between the engine's stages.

These are plain dataclasses on purpose: the AI engine is importable and
testable without a database, a web framework, or a network call. The API
service maps its ORM rows onto these and maps the results back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# --------------------------------------------------------------------------
# Species reference data
# --------------------------------------------------------------------------

SPECIES = ("cattle", "buffalo", "goat", "sheep", "pig", "poultry")

#: Normal rectal temperature range in degrees Celsius, by species.
#: Used to turn a raw thermometer reading into a graded fever signal instead
#: of relying on the farmer's judgement of "hot body".
NORMAL_TEMPERATURE_C: dict[str, tuple[float, float]] = {
    "cattle": (38.0, 39.3),
    "buffalo": (37.5, 39.0),
    "goat": (38.5, 39.7),
    "sheep": (38.5, 39.9),
    "pig": (38.0, 40.0),
    "poultry": (40.5, 42.0),
}

#: Species that share a disease pool closely enough that a cluster in one is
#: epidemiologically relevant to the other (bovines; small ruminants).
SPECIES_GROUP: dict[str, str] = {
    "cattle": "bovine",
    "buffalo": "bovine",
    "goat": "small_ruminant",
    "sheep": "small_ruminant",
    "pig": "porcine",
    "poultry": "avian",
}


class VaccinationStatus(str, Enum):
    UP_TO_DATE = "up_to_date"
    OVERDUE = "overdue"
    NEVER = "never"
    UNKNOWN = "unknown"


class RiskBand(str, Enum):
    """Triage bands. These drive queue ordering and notification routing."""

    ROUTINE = "routine"
    MONITOR = "monitor"
    PRIORITY = "priority"
    URGENT = "urgent"
    EMERGENCY = "emergency"

    @property
    def rank(self) -> int:
        return _BAND_RANK[self]

    @classmethod
    def from_score(cls, score: float) -> "RiskBand":
        if score >= 80:
            return cls.EMERGENCY
        if score >= 60:
            return cls.URGENT
        if score >= 40:
            return cls.PRIORITY
        if score >= 20:
            return cls.MONITOR
        return cls.ROUTINE


_BAND_RANK: dict[RiskBand, int] = {
    RiskBand.ROUTINE: 0,
    RiskBand.MONITOR: 1,
    RiskBand.PRIORITY: 2,
    RiskBand.URGENT: 3,
    RiskBand.EMERGENCY: 4,
}

#: Target response time per band, in hours. Surfaced to the vet queue and used
#: by the analytics layer to compute SLA breaches.
BAND_RESPONSE_TARGET_HOURS: dict[RiskBand, int] = {
    RiskBand.ROUTINE: 168,
    RiskBand.MONITOR: 72,
    RiskBand.PRIORITY: 24,
    RiskBand.URGENT: 6,
    RiskBand.EMERGENCY: 2,
}


@dataclass
class Observation:
    """A single field report, normalised enough for the engine to reason about.

    Most fields are optional because the whole point of the platform is that a
    farmer standing in a field with one bar of signal can still file something
    useful. Missing data lowers ``completeness`` rather than blocking triage.
    """

    report_id: str
    species: str
    reported_at: datetime
    symptoms: list[str] = field(default_factory=list)

    animal_id: str | None = None
    farm_id: str | None = None
    village_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    age_months: int | None = None
    sex: str | None = None
    pregnant: bool = False
    lactating: bool = False

    temperature_c: float | None = None
    duration_hours: int | None = None

    herd_size: int | None = None
    affected_count: int = 1
    deaths_count: int = 0

    vaccination_status: VaccinationStatus = VaccinationStatus.UNKNOWN
    #: How many reports this animal already generated in the last 14 days.
    prior_reports_14d: int = 0
    #: Set by the surveillance layer when the report falls inside a live cluster.
    in_active_cluster: bool = False

    notes: str = ""

    def species_group(self) -> str:
        return SPECIES_GROUP.get(self.species, self.species)


@dataclass
class Contribution:
    """One auditable reason the score moved.

    ``rule_id`` is stable across releases so that an assessment stored last
    month can still be traced back to the rule that produced it.
    """

    rule_id: str
    factor: str
    points: float
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "factor": self.factor,
            "points": round(self.points, 2),
            "evidence": self.evidence,
        }


@dataclass
class StatutoryCaution:
    """A syndromic pattern with public-health or statutory consequences.

    Deliberately *not* a diagnosis. The wording throughout is "consistent
    with", and every caution carries the handling advice that matters before a
    veterinarian arrives -- which for anthrax-like presentations means telling
    people *not* to open the carcass.
    """

    caution_id: str
    title: str
    rationale: str
    actions: tuple[str, ...]
    zoonotic: bool
    notifiable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "caution_id": self.caution_id,
            "title": self.title,
            "rationale": self.rationale,
            "actions": list(self.actions),
            "zoonotic": self.zoonotic,
            "notifiable": self.notifiable,
        }


@dataclass
class RiskAssessment:
    report_id: str
    score: float
    band: RiskBand
    contributions: list[Contribution]
    syndromes: list[str]
    dominant_syndrome: str | None
    cautions: list[StatutoryCaution]
    recommended_action: str
    response_target_hours: int
    #: 0.0 - 1.0 share of decision-relevant fields that were actually supplied.
    completeness: float
    unmatched_terms: list[str]
    engine_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "score": round(self.score, 1),
            "band": self.band.value,
            "contributions": [c.to_dict() for c in self.contributions],
            "syndromes": self.syndromes,
            "dominant_syndrome": self.dominant_syndrome,
            "cautions": [c.to_dict() for c in self.cautions],
            "recommended_action": self.recommended_action,
            "response_target_hours": self.response_target_hours,
            "completeness": round(self.completeness, 2),
            "unmatched_terms": self.unmatched_terms,
            "engine_version": self.engine_version,
        }
