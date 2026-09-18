from datetime import datetime

import pytest

from vanraksha_ai.models import Observation, RiskBand, VaccinationStatus
from vanraksha_ai.risk import RiskEngine

NOW = datetime(2026, 3, 1, 9, 0)


def obs(**kwargs) -> Observation:
    base = dict(report_id="R1", species="cattle", reported_at=NOW)
    base.update(kwargs)
    return Observation(**base)


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine()


def test_empty_report_scores_zero_but_still_returns_a_band(engine):
    result = engine.assess(obs(symptoms=[]))
    assert result.score == 0.0
    assert result.band is RiskBand.ROUTINE
    assert result.recommended_action


def test_score_is_the_sum_of_its_contributions(engine):
    result = engine.assess(
        obs(symptoms=["fever", "cough"], temperature_c=40.5, herd_size=20, affected_count=3)
    )
    assert result.score == pytest.approx(
        min(100.0, sum(c.points for c in result.contributions)), abs=0.01
    )


def test_every_contribution_carries_an_auditable_reason(engine):
    result = engine.assess(obs(symptoms=["fever"], temperature_c=41.0))
    assert result.contributions
    for contribution in result.contributions:
        assert contribution.rule_id
        assert contribution.evidence.strip()


def test_severity_ordering_is_monotonic(engine):
    mild = engine.assess(obs(symptoms=["ticks"]))
    moderate = engine.assess(obs(symptoms=["fever", "diarrhoea"]))
    severe = engine.assess(obs(symptoms=["laboured breathing", "cannot stand"]))
    assert mild.score < moderate.score < severe.score


def test_species_specific_temperature_reference(engine):
    # 41.0 C is a clear fever in cattle and inside the normal range for poultry.
    cattle = engine.assess(obs(species="cattle", symptoms=["fever"], temperature_c=41.0))
    poultry = engine.assess(obs(species="poultry", symptoms=["fever"], temperature_c=41.0))
    assert any(c.rule_id == "VITAL.010" for c in cattle.contributions)
    assert any(c.rule_id == "VITAL.030" for c in poultry.contributions)
    assert cattle.score > poultry.score


def test_hypothermia_is_scored_as_a_danger_sign(engine):
    result = engine.assess(obs(symptoms=["lethargy"], temperature_c=36.5))
    assert any(c.rule_id == "VITAL.020" for c in result.contributions)


def test_herd_spread_raises_the_score(engine):
    single = engine.assess(obs(symptoms=["fever"], herd_size=30, affected_count=1))
    many = engine.assess(obs(symptoms=["fever"], herd_size=30, affected_count=12))
    assert many.score > single.score
    assert any(c.rule_id == "SPREAD.020" for c in many.contributions)


def test_deaths_escalate_beyond_signs_alone(engine):
    alive = engine.assess(obs(symptoms=["fever"], herd_size=10))
    dead = engine.assess(obs(symptoms=["fever"], herd_size=10, deaths_count=2))
    assert dead.score > alive.score + 8


def test_up_to_date_vaccination_lowers_the_score(engine):
    unknown = engine.assess(obs(symptoms=["fever"], vaccination_status=VaccinationStatus.UNKNOWN))
    current = engine.assess(obs(symptoms=["fever"], vaccination_status=VaccinationStatus.UP_TO_DATE))
    assert current.score < unknown.score


def test_vaccination_gap_only_counts_for_relevant_presentations(engine):
    # Lameness is not vaccine-preventable; an overdue shot must not escalate it.
    result = engine.assess(obs(symptoms=["lameness"], vaccination_status=VaccinationStatus.NEVER))
    assert not any(c.rule_id.startswith("PREV") for c in result.contributions)


def test_active_cluster_context_raises_priority(engine):
    alone = engine.assess(obs(symptoms=["fever", "cough"]))
    in_cluster = engine.assess(obs(symptoms=["fever", "cough"], in_active_cluster=True))
    assert in_cluster.score > alone.score


def test_score_is_clamped_to_one_hundred(engine):
    result = engine.assess(
        obs(
            symptoms=["found dead", "blood from nose", "convulsions", "cannot stand"],
            temperature_c=43.0, herd_size=10, affected_count=10, deaths_count=8,
            age_months=2, pregnant=True, lactating=True, prior_reports_14d=5,
            vaccination_status=VaccinationStatus.NEVER, in_active_cluster=True,
        )
    )
    assert result.score == 100.0
    assert result.band is RiskBand.EMERGENCY


def test_completeness_reflects_supplied_fields(engine):
    sparse = engine.assess(obs(symptoms=["fever"]))
    rich = engine.assess(
        obs(
            symptoms=["fever"], temperature_c=40.0, duration_hours=24, herd_size=10,
            latitude=12.9, longitude=77.6, age_months=36,
            vaccination_status=VaccinationStatus.UP_TO_DATE,
        )
    )
    assert rich.completeness > sparse.completeness
    assert 0.0 <= sparse.completeness <= 1.0


def test_unmatched_terms_are_surfaced(engine):
    result = engine.assess(obs(symptoms=["fever", "walking oddly sideways at dusk"]))
    assert result.unmatched_terms == ["walking oddly sideways at dusk"]


def test_assessment_serialises_to_plain_json_types(engine):
    import json

    payload = engine.assess(obs(symptoms=["fever", "cough"], temperature_c=40.2)).to_dict()
    assert json.loads(json.dumps(payload))["band"] in {b.value for b in RiskBand}


class TestStatutoryCautions:
    """The floor rules: patterns where waiting for the arithmetic is wrong."""

    def test_sudden_death_with_bleeding_reaches_emergency_despite_low_score(self, engine):
        result = engine.assess(obs(symptoms=["found dead", "blood from nose"], deaths_count=1))
        assert result.band is RiskBand.EMERGENCY
        assert result.score < 80  # the floor did the work, not the sum
        ids = [c.caution_id for c in result.cautions]
        assert "anthrax_like" in ids
        anthrax = next(c for c in result.cautions if c.caution_id == "anthrax_like")
        assert anthrax.zoonotic and anthrax.notifiable
        assert any("do not open" in a.lower() for a in anthrax.actions)

    def test_vesicular_signs_trigger_movement_restriction(self, engine):
        result = engine.assess(obs(symptoms=["mouth ulcer", "drooling"]))
        assert result.band.rank >= RiskBand.URGENT.rank
        assert "fmd_like" in [c.caution_id for c in result.cautions]

    def test_neurological_signs_put_handler_safety_first(self, engine):
        result = engine.assess(obs(symptoms=["sudden aggression", "frothing"]))
        assert result.band is RiskBand.EMERGENCY
        rabies = next(c for c in result.cautions if c.caution_id == "rabies_like")
        assert rabies.zoonotic
        assert any("wash the wound" in a.lower() for a in rabies.actions)

    def test_single_abortion_is_not_a_cluster(self, engine):
        single = engine.assess(obs(symptoms=["abortion"], affected_count=1))
        several = engine.assess(obs(symptoms=["abortion"], affected_count=3))
        assert "abortion_cluster" not in [c.caution_id for c in single.cautions]
        assert "abortion_cluster" in [c.caution_id for c in several.cautions]

    def test_species_gating(self, engine):
        # Nodular skin disease caution is bovine-specific.
        cow = engine.assess(obs(species="cattle", symptoms=["lumps on skin", "fever"]))
        goat = engine.assess(obs(species="goat", symptoms=["lumps on skin", "fever"]))
        assert "nodular_skin" in [c.caution_id for c in cow.cautions]
        assert "nodular_skin" not in [c.caution_id for c in goat.cautions]

    def test_floor_is_recorded_as_a_contribution(self, engine):
        result = engine.assess(obs(symptoms=["mouth ulcer"]))
        assert any(c.rule_id.startswith("FLOOR.") for c in result.contributions)

    def test_no_caution_claims_a_diagnosis(self, engine):
        """Every caution must be phrased as a pattern, never as a disease the
        animal has. This is the guarantee the whole positioning rests on."""
        from vanraksha_ai.risk import cautions as catalogue

        banned = ("diagnosed with", "the animal has", "confirmed case of", "this is anthrax")
        for _, caution in catalogue.CAUTION_RULES:
            text = f"{caution.title} {caution.rationale}".lower()
            for phrase in banned:
                assert phrase not in text, f"{caution.caution_id} reads as a diagnosis"
