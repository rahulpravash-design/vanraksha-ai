"""Deterministic, explainable triage scoring.

Design constraints this file exists to satisfy:

1. **Every point is attributable.** The score is a sum of named contributions,
   each carrying a stable ``rule_id`` and a human-readable evidence string. If
   a veterinarian asks why a report scored 62, the answer is a list, not a
   shrug. No component of the score comes from an opaque model.
2. **Missing data degrades, never blocks.** A report with three words of text
   and no thermometer reading still produces a band; it just carries a lower
   ``completeness`` so reviewers know how much to lean on it.
3. **Some patterns outrank arithmetic.** A single dead animal with bleeding
   from the orifices scores modestly on herd impact and must still reach the
   top band. Cautions therefore impose a *floor* on the band after scoring.

The learned models in ``ml/`` are evaluated against this engine as a baseline
and, where they win, feed it as an additional contribution -- they do not
replace it. A rule that a vet can read and challenge is worth more in the field
than a percentage nobody can interrogate.
"""

from __future__ import annotations

from typing import Iterable

from ..models import (
    BAND_RESPONSE_TARGET_HOURS,
    NORMAL_TEMPERATURE_C,
    Contribution,
    Observation,
    RiskAssessment,
    RiskBand,
    VaccinationStatus,
)
from .. import taxonomy
from . import cautions as caution_rules

ENGINE_VERSION = "risk-engine/1.2.0"

# Per-component ceilings. They sum above 100 on purpose: a report can be
# alarming for more than one reason, and the clamp at the end is what keeps the
# scale interpretable.
CAP_SIGNS = 32.0
CAP_VITALS = 14.0
CAP_SPREAD = 24.0
CAP_MORTALITY = 20.0
CAP_VULNERABILITY = 10.0
CAP_PREVENTION = 8.0
CAP_PROGRESSION = 8.0
CAP_CONTEXT = 10.0

#: Fields that a reviewer would want before acting on a report. Used for the
#: completeness figure shown next to every score.
_COMPLETENESS_FIELDS = (
    "symptoms", "species", "location", "temperature", "duration",
    "herd_size", "affected_count", "vaccination_status", "animal_age",
)

_ACTIONS: dict[RiskBand, str] = {
    RiskBand.ROUTINE: (
        "Record and monitor. No veterinary visit indicated on current information; "
        "ask the farmer to re-report if signs persist beyond 72 hours or worsen."
    ),
    RiskBand.MONITOR: (
        "Monitor daily and advise supportive care. Route to the field worker for a "
        "check-in; escalate if new signs appear or the animal stops feeding entirely."
    ),
    RiskBand.PRIORITY: (
        "Schedule a veterinary examination within the working day. Isolate the animal "
        "from the rest of the herd until it has been seen."
    ),
    RiskBand.URGENT: (
        "Assign a veterinarian now and isolate the affected animals. Restrict movement "
        "on and off the premises until the visit has taken place."
    ),
    RiskBand.EMERGENCY: (
        "Dispatch immediately and notify the block veterinary officer. Apply the handling "
        "precautions listed below before anyone approaches the animal or carcass."
    ),
}


class RiskEngine:
    """Scores a single observation. Stateless and safe to share across threads."""

    version = ENGINE_VERSION

    def assess(self, obs: Observation) -> RiskAssessment:
        normalised = taxonomy.normalise(obs.symptoms)
        codes = normalised.codes
        code_set = set(codes)

        contributions: list[Contribution] = []
        contributions.extend(self._score_signs(codes))
        contributions.extend(self._score_vitals(obs, code_set))
        contributions.extend(self._score_spread(obs))
        contributions.extend(self._score_mortality(obs))
        contributions.extend(self._score_vulnerability(obs))
        contributions.extend(self._score_prevention(obs, code_set))
        contributions.extend(self._score_progression(obs))
        contributions.extend(self._score_context(obs))

        score = max(0.0, min(100.0, sum(c.points for c in contributions)))
        band = RiskBand.from_score(score)

        matched = caution_rules.evaluate(code_set, obs)
        band = self._apply_caution_floor(band, matched, contributions)

        contributions.sort(key=lambda c: abs(c.points), reverse=True)

        return RiskAssessment(
            report_id=obs.report_id,
            score=score,
            band=band,
            contributions=contributions,
            syndromes=normalised.syndromes,
            dominant_syndrome=taxonomy.dominant_syndrome(codes),
            cautions=matched,
            recommended_action=_ACTIONS[band],
            response_target_hours=BAND_RESPONSE_TARGET_HOURS[band],
            completeness=self._completeness(obs, codes),
            unmatched_terms=normalised.unmatched,
            engine_version=ENGINE_VERSION,
        )

    # ------------------------------------------------------------------ signs

    def _score_signs(self, codes: list[str]) -> list[Contribution]:
        if not codes:
            return [
                Contribution(
                    rule_id="SIGN.000",
                    factor="Clinical signs",
                    points=0.0,
                    evidence="No recognised clinical sign in the report text.",
                )
            ]

        out: list[Contribution] = []
        worst = max(codes, key=lambda c: taxonomy.BY_CODE[c].severity_weight
                    if c in taxonomy.BY_CODE else 0.0)
        worst_weight = taxonomy.severity_of(codes)
        points = round(26.0 * worst_weight, 2)
        out.append(
            Contribution(
                rule_id="SIGN.010",
                factor="Most severe sign",
                points=points,
                evidence=(
                    f"{taxonomy.label_for(worst)} carries a severity weight of "
                    f"{worst_weight:.2f} in the clinical taxonomy."
                ),
            )
        )

        # Breadth matters independently: a multi-system presentation is worse
        # than the same worst sign on its own.
        extra = len(codes) - 1
        if extra > 0:
            breadth = round(min(6.0, 1.5 * extra), 2)
            out.append(
                Contribution(
                    rule_id="SIGN.020",
                    factor="Breadth of presentation",
                    points=breadth,
                    evidence=(
                        f"{len(codes)} distinct signs reported across "
                        f"{len(taxonomy.syndromes_for(codes))} syndromic group(s)."
                    ),
                )
            )

        total = sum(c.points for c in out)
        if total > CAP_SIGNS:
            out.append(self._cap("SIGN.CAP", "Clinical signs", CAP_SIGNS - total))
        return out

    # ----------------------------------------------------------------- vitals

    def _score_vitals(self, obs: Observation, codes: set[str]) -> list[Contribution]:
        temp = obs.temperature_c
        if temp is None:
            return []

        low, high = NORMAL_TEMPERATURE_C.get(obs.species, (38.0, 39.5))

        if temp > high:
            excess = temp - high
            points = round(min(CAP_VITALS, 9.0 * excess), 2)
            return [
                Contribution(
                    rule_id="VITAL.010",
                    factor="Pyrexia",
                    points=points,
                    evidence=(
                        f"Rectal temperature {temp:.1f} degrees C is {excess:.1f} above the "
                        f"{obs.species} normal upper limit of {high:.1f}."
                    ),
                )
            ]

        if temp < low:
            deficit = low - temp
            # Subnormal temperature in a sick animal is a late, poor-prognosis
            # sign, so it is weighted more heavily per degree than fever.
            points = round(min(CAP_VITALS, 12.0 * deficit), 2)
            return [
                Contribution(
                    rule_id="VITAL.020",
                    factor="Hypothermia",
                    points=points,
                    evidence=(
                        f"Rectal temperature {temp:.1f} degrees C is {deficit:.1f} below the "
                        f"{obs.species} normal lower limit of {low:.1f}; subnormal temperature "
                        "in a symptomatic animal suggests decompensation."
                    ),
                )
            ]

        return [
            Contribution(
                rule_id="VITAL.030",
                factor="Temperature within range",
                points=0.0,
                evidence=(
                    f"Rectal temperature {temp:.1f} degrees C is inside the {obs.species} "
                    f"normal range {low:.1f}-{high:.1f}."
                ),
            )
        ]

    # ----------------------------------------------------------------- spread

    def _score_spread(self, obs: Observation) -> list[Contribution]:
        out: list[Contribution] = []
        affected = max(1, obs.affected_count)

        if affected > 1:
            out.append(
                Contribution(
                    rule_id="SPREAD.010",
                    factor="Multiple animals affected",
                    points=round(min(12.0, 4.0 * (affected - 1) ** 0.75), 2),
                    evidence=f"{affected} animals reported with the same presentation.",
                )
            )

        if obs.herd_size and obs.herd_size > 0:
            fraction = min(1.0, affected / obs.herd_size)
            if fraction >= 0.10:
                out.append(
                    Contribution(
                        rule_id="SPREAD.020",
                        factor="Herd attack rate",
                        points=round(min(12.0, 14.0 * fraction), 2),
                        evidence=(
                            f"{affected} of {obs.herd_size} animals affected "
                            f"({fraction * 100:.0f}% of the herd)."
                        ),
                    )
                )

        total = sum(c.points for c in out)
        if total > CAP_SPREAD:
            out.append(self._cap("SPREAD.CAP", "Spread within herd", CAP_SPREAD - total))
        return out

    # -------------------------------------------------------------- mortality

    def _score_mortality(self, obs: Observation) -> list[Contribution]:
        if obs.deaths_count <= 0:
            return []

        out = [
            Contribution(
                rule_id="MORT.010",
                factor="Deaths reported",
                points=round(min(14.0, 8.0 + 3.0 * (obs.deaths_count - 1)), 2),
                evidence=f"{obs.deaths_count} death(s) reported in this event.",
            )
        ]

        if obs.herd_size and obs.herd_size > 0:
            rate = obs.deaths_count / obs.herd_size
            if rate >= 0.02:
                out.append(
                    Contribution(
                        rule_id="MORT.020",
                        factor="Case mortality rate",
                        points=round(min(10.0, 40.0 * rate), 2),
                        evidence=(
                            f"{obs.deaths_count} death(s) in a herd of {obs.herd_size} "
                            f"({rate * 100:.1f}% mortality)."
                        ),
                    )
                )

        total = sum(c.points for c in out)
        if total > CAP_MORTALITY:
            out.append(self._cap("MORT.CAP", "Mortality", CAP_MORTALITY - total))
        return out

    # ---------------------------------------------------------- vulnerability

    def _score_vulnerability(self, obs: Observation) -> list[Contribution]:
        out: list[Contribution] = []

        if obs.age_months is not None:
            if obs.age_months <= 3:
                out.append(
                    Contribution(
                        rule_id="VULN.010",
                        factor="Neonate / young stock",
                        points=5.0,
                        evidence=(
                            f"Animal is {obs.age_months} month(s) old; young stock "
                            "decompensate faster and tolerate fluid loss poorly."
                        ),
                    )
                )
            elif obs.age_months >= 120:
                out.append(
                    Contribution(
                        rule_id="VULN.020",
                        factor="Aged animal",
                        points=2.0,
                        evidence=f"Animal is {obs.age_months // 12} years old.",
                    )
                )

        if obs.pregnant:
            out.append(
                Contribution(
                    rule_id="VULN.030",
                    factor="Pregnant",
                    points=4.0,
                    evidence="Pregnancy raises both the clinical stakes and the treatment constraints.",
                )
            )

        if obs.lactating:
            out.append(
                Contribution(
                    rule_id="VULN.040",
                    factor="Lactating",
                    points=2.0,
                    evidence="Lactating animal: milk withdrawal and food-safety implications apply.",
                )
            )

        total = sum(c.points for c in out)
        if total > CAP_VULNERABILITY:
            out.append(self._cap("VULN.CAP", "Vulnerability", CAP_VULNERABILITY - total))
        return out

    # --------------------------------------------------------------- prevention

    def _score_prevention(self, obs: Observation, codes: set[str]) -> list[Contribution]:
        # Only counts when the presentation is one that vaccination bears on --
        # an overdue vaccination is not a reason to escalate a lame animal.
        relevant = bool(
            {"fever", "oral_lesions", "foot_lesions", "skin_nodules", "abortion",
             "nasal_discharge", "dyspnoea", "sudden_death"} & codes
        )
        if not relevant:
            return []

        if obs.vaccination_status == VaccinationStatus.NEVER:
            return [
                Contribution(
                    rule_id="PREV.010",
                    factor="Never vaccinated",
                    points=8.0,
                    evidence="No vaccination on record for an animal with a vaccine-preventable presentation.",
                )
            ]
        if obs.vaccination_status == VaccinationStatus.OVERDUE:
            return [
                Contribution(
                    rule_id="PREV.020",
                    factor="Vaccination overdue",
                    points=5.0,
                    evidence="Scheduled vaccination is past due for this animal.",
                )
            ]
        if obs.vaccination_status == VaccinationStatus.UNKNOWN:
            return [
                Contribution(
                    rule_id="PREV.030",
                    factor="Vaccination status unknown",
                    points=2.0,
                    evidence="No vaccination history available; treated as a partial protection gap.",
                )
            ]
        return [
            Contribution(
                rule_id="PREV.040",
                factor="Vaccination up to date",
                points=-2.0,
                evidence="Vaccination is current, which lowers the prior for a vaccine-preventable cause.",
            )
        ]

    # -------------------------------------------------------------- progression

    def _score_progression(self, obs: Observation) -> list[Contribution]:
        out: list[Contribution] = []

        if obs.duration_hours is not None:
            if obs.duration_hours >= 72:
                out.append(
                    Contribution(
                        rule_id="PROG.010",
                        factor="Persistent signs",
                        points=4.0,
                        evidence=(
                            f"Signs have been present for about {obs.duration_hours // 24} day(s) "
                            "without resolution."
                        ),
                    )
                )
            elif obs.duration_hours <= 6:
                out.append(
                    Contribution(
                        rule_id="PROG.020",
                        factor="Peracute onset",
                        points=3.0,
                        evidence=(
                            f"Onset within the last {obs.duration_hours} hour(s); rapid onset "
                            "narrows the window for effective intervention."
                        ),
                    )
                )

        if obs.prior_reports_14d >= 2:
            out.append(
                Contribution(
                    rule_id="PROG.030",
                    factor="Repeat reporting",
                    points=round(min(5.0, 2.0 * obs.prior_reports_14d), 2),
                    evidence=(
                        f"{obs.prior_reports_14d} previous report(s) for this animal in 14 days "
                        "suggests the earlier response did not resolve the problem."
                    ),
                )
            )

        total = sum(c.points for c in out)
        if total > CAP_PROGRESSION:
            out.append(self._cap("PROG.CAP", "Progression", CAP_PROGRESSION - total))
        return out

    # ----------------------------------------------------------------- context

    def _score_context(self, obs: Observation) -> list[Contribution]:
        if not obs.in_active_cluster:
            return []
        return [
            Contribution(
                rule_id="CTX.010",
                factor="Inside an active cluster",
                points=CAP_CONTEXT,
                evidence=(
                    "This report falls inside a live geo-temporal cluster, so it is part of "
                    "an event already under investigation rather than an isolated case."
                ),
            )
        ]

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _cap(rule_id: str, factor: str, adjustment: float) -> Contribution:
        return Contribution(
            rule_id=rule_id,
            factor=f"{factor} (capped)",
            points=round(adjustment, 2),
            evidence="Component ceiling applied so no single factor can dominate the score.",
        )

    @staticmethod
    def _apply_caution_floor(
        band: RiskBand,
        matched: Iterable,
        contributions: list[Contribution],
    ) -> RiskBand:
        for caution in matched:
            floor_name = caution_rules.CAUTION_MIN_BAND.get(caution.caution_id)
            if not floor_name:
                continue
            floor = RiskBand(floor_name)
            if floor.rank > band.rank:
                contributions.append(
                    Contribution(
                        rule_id=f"FLOOR.{caution.caution_id}",
                        factor="Band floor applied",
                        points=0.0,
                        evidence=(
                            f"Raised from {band.value} to {floor.value}: the presentation matches "
                            f"'{caution.title}', where the correct first action does not wait on "
                            "the arithmetic score."
                        ),
                    )
                )
                band = floor
        return band

    @staticmethod
    def _completeness(obs: Observation, codes: list[str]) -> float:
        present = 0
        if codes:
            present += 1
        if obs.species:
            present += 1
        if obs.latitude is not None and obs.longitude is not None:
            present += 1
        if obs.temperature_c is not None:
            present += 1
        if obs.duration_hours is not None:
            present += 1
        if obs.herd_size:
            present += 1
        if obs.affected_count:
            present += 1
        if obs.vaccination_status != VaccinationStatus.UNKNOWN:
            present += 1
        if obs.age_months is not None:
            present += 1
        return present / len(_COMPLETENESS_FIELDS)


#: Module-level singleton for the common case.
default_engine = RiskEngine()


def assess(obs: Observation) -> RiskAssessment:
    return default_engine.assess(obs)
