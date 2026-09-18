"""Request and response contracts.

Validation here is the first line of data quality. A farmer reporting 300
deaths in a herd of 12 is a typo, and catching it at the boundary is far
cheaper than letting it distort a district mortality dashboard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import AnimalStatus, CaseStatus, ClusterStatus, Role

SPECIES = ("cattle", "buffalo", "goat", "sheep", "pig", "poultry")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------- auth


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Role
    user_id: str
    full_name: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    full_name: str = Field(min_length=2, max_length=160)
    role: Role = Role.FARMER
    phone: str | None = Field(default=None, max_length=20)
    language: str = Field(default="en", max_length=8)
    village_id: str | None = None
    block: str | None = None
    district: str | None = None

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes when UTF-8 encoded")
        if value.lower() in {"password12", "1234567890", "vanraksha1"}:
            raise ValueError("password is too common")
        return value


class UserOut(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    phone: str | None = None
    language: str
    village_id: str | None = None
    block: str | None = None
    district: str | None = None
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------------ geography


class VillageOut(ORMModel):
    id: str
    name: str
    block: str
    district: str
    state: str
    latitude: float
    longitude: float
    livestock_population: int


# --------------------------------------------------------------------- farms


class FarmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    village_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class FarmOut(ORMModel):
    id: str
    name: str
    owner_id: str
    village_id: str
    latitude: float
    longitude: float
    herd_size: int
    created_at: datetime


# ------------------------------------------------------------------- animals


class AnimalCreate(BaseModel):
    tag: str = Field(min_length=1, max_length=64)
    species: str
    farm_id: str
    breed: str | None = Field(default=None, max_length=80)
    sex: str | None = None
    date_of_birth: datetime | None = None
    is_pregnant: bool = False
    is_lactating: bool = False

    @field_validator("species")
    @classmethod
    def _known_species(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in SPECIES:
            raise ValueError(f"species must be one of: {', '.join(SPECIES)}")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_the_future(cls, value: datetime | None) -> datetime | None:
        if value and value > datetime.utcnow():
            raise ValueError("date of birth cannot be in the future")
        return value


class AnimalUpdate(BaseModel):
    breed: str | None = None
    status: AnimalStatus | None = None
    is_pregnant: bool | None = None
    is_lactating: bool | None = None


class AnimalOut(ORMModel):
    id: str
    tag: str
    species: str
    breed: str | None = None
    sex: str | None = None
    date_of_birth: datetime | None = None
    farm_id: str
    status: AnimalStatus
    is_pregnant: bool
    is_lactating: bool
    age_months: int | None = None
    created_at: datetime


# ------------------------------------------------------------------- reports


class HealthReportCreate(BaseModel):
    """A field report.

    ``client_uuid`` is generated on the device before submission so that a
    report queued offline and retried after a dropped connection is stored once,
    not three times.
    """

    client_uuid: str = Field(min_length=8, max_length=64)
    species: str
    symptoms: list[str] = Field(default_factory=list, max_length=40)
    symptoms_text: str = Field(default="", max_length=4000)

    animal_id: str | None = None
    farm_id: str | None = None
    village_id: str | None = None
    reported_at: datetime | None = None

    temperature_c: float | None = Field(default=None, ge=25.0, le=46.0)
    duration_hours: int | None = Field(default=None, ge=0, le=24 * 365)
    affected_count: int = Field(default=1, ge=1, le=100_000)
    deaths_count: int = Field(default=0, ge=0, le=100_000)
    herd_size: int | None = Field(default=None, ge=1, le=1_000_000)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str = Field(default="", max_length=4000)
    submitted_offline: bool = False

    @field_validator("species")
    @classmethod
    def _known_species(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in SPECIES:
            raise ValueError(f"species must be one of: {', '.join(SPECIES)}")
        return value

    @field_validator("reported_at")
    @classmethod
    def _not_in_the_future(cls, value: datetime | None) -> datetime | None:
        # A few minutes of clock skew on a field device is normal; a week is a
        # wrong date that would land the report in the wrong surveillance window.
        if value and (value - datetime.utcnow()).total_seconds() > 3600:
            raise ValueError("reported_at cannot be more than an hour in the future")
        return value

    @model_validator(mode="after")
    def _internally_consistent(self) -> "HealthReportCreate":
        if self.herd_size is not None and self.affected_count > self.herd_size:
            raise ValueError("affected_count cannot exceed herd_size")
        if self.deaths_count > self.affected_count:
            raise ValueError("deaths_count cannot exceed affected_count")
        if not self.symptoms and not self.symptoms_text.strip() and self.deaths_count == 0:
            raise ValueError(
                "a report needs at least one symptom, some description, or a death count"
            )
        # Coordinates only mean something as a pair.
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class ContributionOut(BaseModel):
    rule_id: str
    factor: str
    points: float
    evidence: str


class CautionOut(BaseModel):
    caution_id: str
    title: str
    rationale: str
    actions: list[str]
    zoonotic: bool
    notifiable: bool


class AssessmentOut(ORMModel):
    id: str
    report_id: str
    score: float
    band: str
    contributions: list[ContributionOut]
    syndromes: list[str]
    dominant_syndrome: str | None = None
    cautions: list[CautionOut]
    recommended_action: str
    response_target_hours: int
    completeness: float
    engine_version: str
    created_at: datetime


class HealthReportOut(ORMModel):
    id: str
    client_uuid: str
    animal_id: str | None = None
    farm_id: str | None = None
    village_id: str | None = None
    reporter_id: str
    species: str
    reported_at: datetime
    received_at: datetime
    symptoms_text: str
    symptom_codes: list[str]
    unmatched_terms: list[str]
    temperature_c: float | None = None
    duration_hours: int | None = None
    affected_count: int
    deaths_count: int
    herd_size: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str
    submitted_offline: bool
    assessment: AssessmentOut | None = None


# --------------------------------------------------------------------- cases


class CaseOut(ORMModel):
    id: str
    report_id: str
    status: CaseStatus
    band: str
    assigned_vet_id: str | None = None
    opened_at: datetime
    assigned_at: datetime | None = None
    first_response_at: datetime | None = None
    closed_at: datetime | None = None
    due_at: datetime | None = None
    outcome: str | None = None
    resolution_notes: str
    cluster_id: str | None = None
    is_overdue: bool = False


class CaseAssign(BaseModel):
    veterinarian_id: str


class CaseUpdate(BaseModel):
    status: CaseStatus | None = None
    outcome: str | None = Field(default=None, max_length=64)
    resolution_notes: str | None = Field(default=None, max_length=4000)


# -------------------------------------------------------------- vaccinations


class VaccinationCreate(BaseModel):
    animal_id: str
    vaccine: str = Field(min_length=2, max_length=80)
    administered_on: datetime
    next_due_on: datetime | None = None
    batch_number: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _ordering(self) -> "VaccinationCreate":
        if self.next_due_on and self.next_due_on <= self.administered_on:
            raise ValueError("next_due_on must be after administered_on")
        return self


class VaccinationOut(ORMModel):
    id: str
    animal_id: str
    vaccine: str
    administered_on: datetime
    next_due_on: datetime | None = None
    batch_number: str | None = None
    administered_by: str | None = None


# ---------------------------------------------------------------- treatments


class TreatmentCreate(BaseModel):
    animal_id: str
    case_id: str | None = None
    administered_on: datetime
    description: str = Field(min_length=3, max_length=4000)
    withdrawal_until: datetime | None = None


class TreatmentOut(ORMModel):
    id: str
    animal_id: str
    case_id: str | None = None
    administered_on: datetime
    description: str
    administered_by: str
    withdrawal_until: datetime | None = None


# ------------------------------------------------------------------ clusters


class ClusterOut(ORMModel):
    id: str
    signature: str
    status: ClusterStatus
    centroid_lat: float
    centroid_lon: float
    radius_km: float
    first_seen: datetime
    last_seen: datetime
    report_count: int
    animal_count: int
    death_count: int
    severity_score: float
    growth_ratio: float
    dominant_syndrome: str | None = None
    villages: list[str]
    species: list[str]
    report_ids: list[str]
    top_symptoms: list[dict[str, Any]]
    explanation: str
    detector_version: str
    detected_at: datetime
    review_outcome: str | None = None
    review_notes: str


class ClusterReview(BaseModel):
    outcome: str = Field(pattern="^(confirmed|dismissed|under_investigation|resolved)$")
    notes: str = Field(default="", max_length=4000)


# -------------------------------------------------------------------- alerts


class AlertOut(ORMModel):
    id: str
    dedupe_key: str
    kind: str
    severity: float
    title: str
    body: str
    scope: str
    audiences: list[str]
    evidence: dict[str, Any]
    raised_at: datetime
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


# ---------------------------------------------------------------------- sync


class SyncBatch(BaseModel):
    """A batch of reports queued while the device was offline."""

    reports: list[HealthReportCreate] = Field(max_length=200)
    device_id: str | None = Field(default=None, max_length=64)


class SyncItemResult(BaseModel):
    client_uuid: str
    status: str  # accepted | duplicate | rejected
    report_id: str | None = None
    band: str | None = None
    detail: str | None = None


class SyncResult(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    results: list[SyncItemResult]
    server_time: datetime


# ----------------------------------------------------------------- analytics


class TimeseriesPoint(BaseModel):
    period_start: str
    count: float


class ScopeSummary(BaseModel):
    scope: str
    period_days: int
    report_count: int
    previous_period_count: int
    animal_count: int
    death_count: int
    open_cases: int
    overdue_cases: int
    active_clusters: int
    overdue_vaccinations: int
    band_counts: dict[str, int]
    syndrome_counts: dict[str, int]
    top_symptoms: list[dict[str, Any]]
    weekly_series: list[TimeseriesPoint]
    trend: str


class AssistantQuery(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    scope: str | None = Field(default=None, max_length=120)
    days: int = Field(default=30, ge=1, le=365)


class AssistantAnswer(BaseModel):
    answer: str
    source: str
    grounded_in: str
    guardrail: str | None = None
    assistant_version: str
