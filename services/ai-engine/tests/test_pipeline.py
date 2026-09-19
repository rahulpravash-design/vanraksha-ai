from datetime import datetime, timedelta

import pytest

from vanraksha_ai import Observation, RiskBand, SurveillancePipeline, VaccinationStatus
from vanraksha_ai.pipeline import AlertKind, Audience

NOW = datetime(2026, 3, 20, 9, 0)


def report(pid, *, hours_ago=0, symptoms=("fever", "cough"), village="V-Alpha",
           dlat=0.0, dlon=0.0, **kwargs):
    return Observation(
        report_id=pid,
        species=kwargs.pop("species", "cattle"),
        reported_at=NOW - timedelta(hours=hours_ago),
        symptoms=list(symptoms),
        latitude=12.90 + dlat,
        longitude=77.60 + dlon,
        village_id=village,
        **kwargs,
    )


@pytest.fixture
def pipeline() -> SurveillancePipeline:
    return SurveillancePipeline()


class TestTriageStage:
    def test_triage_returns_one_assessment_per_report(self, pipeline):
        results = pipeline.triage_many([report("R1"), report("R2")])
        assert [r.report_id for r in results] == ["R1", "R2"]

    def test_triage_works_without_a_location(self, pipeline):
        """A report filed with no GPS fix must still get a band."""
        observation = Observation(
            report_id="R1", species="goat", reported_at=NOW, symptoms=["fever"]
        )
        assert pipeline.triage(observation).band is not None


class TestSweep:
    def test_a_cluster_produces_a_routed_alert(self, pipeline):
        reports = [
            report(f"R{i}", hours_ago=i * 12, dlat=0.004 * i, herd_size=15, affected_count=2)
            for i in range(6)
        ]
        result = pipeline.sweep(reports, now=NOW, scope_label="Hoskote block")

        assert len(result.clusters) == 1
        cluster_alerts = [a for a in result.alerts if a.kind is AlertKind.CLUSTER]
        assert len(cluster_alerts) == 1
        assert Audience.VETERINARIAN in cluster_alerts[0].audiences
        assert Audience.BLOCK_ADMIN in cluster_alerts[0].audiences
        assert cluster_alerts[0].evidence["report_ids"]

    def test_an_emergency_case_alerts_on_its_own(self, pipeline):
        reports = [report("RX", symptoms=["found dead", "blood from nose"], deaths_count=1)]
        result = pipeline.sweep(reports, now=NOW)

        case_alerts = [a for a in result.alerts if a.kind is AlertKind.CASE]
        assert len(case_alerts) == 1
        assert Audience.DISTRICT_ADMIN in case_alerts[0].audiences
        assert case_alerts[0].evidence["band"] == "emergency"
        assert "anthrax_like" in case_alerts[0].evidence["cautions"]

    def test_routine_reports_raise_no_case_alert(self, pipeline):
        result = pipeline.sweep([report("R1", symptoms=["ticks"])], now=NOW)
        assert not [a for a in result.alerts if a.kind is AlertKind.CASE]

    def test_alerts_are_ordered_by_severity(self, pipeline):
        reports = [report(f"R{i}", hours_ago=i * 12, dlat=0.004 * i) for i in range(5)]
        reports.append(report("RX", symptoms=["found dead", "blood from nose"], deaths_count=1))
        result = pipeline.sweep(reports, now=NOW)
        severities = [a.severity for a in result.alerts]
        assert severities == sorted(severities, reverse=True)

    def test_a_low_severity_cluster_stays_local(self, pipeline):
        reports = [report(f"R{i}", hours_ago=i * 20, dlat=0.003 * i) for i in range(3)]
        result = pipeline.sweep(reports, now=NOW)
        for alert in result.alerts:
            if alert.kind is AlertKind.CLUSTER and alert.severity < 55:
                assert Audience.DISTRICT_ADMIN not in alert.audiences

    def test_reports_without_coordinates_are_still_triaged(self, pipeline):
        """Missing GPS removes a report from clustering, not from the queue."""
        located = [report(f"R{i}", hours_ago=i * 12, dlat=0.004 * i) for i in range(4)]
        unlocated = Observation(
            report_id="NOGPS", species="cattle", reported_at=NOW,
            symptoms=["laboured breathing"], village_id="V-Alpha",
        )
        result = pipeline.sweep(located + [unlocated], now=NOW)
        assert len(result.assessments) == 5
        assert "NOGPS" not in [pid for c in result.clusters for pid in c.point_ids]

    def test_free_text_and_coded_symptoms_cluster_together(self, pipeline):
        """A farmer typing 'loose motion' and a vet coding 'diarrhoea' describe
        the same event, so they must land in the same cluster."""
        # Four reports, because that is the detection threshold; the point of
        # the test is that all four land together despite three different
        # spellings of the same sign.
        reports = [
            report("R0", symptoms=["loose motion"], dlat=0.000, hours_ago=0),
            report("R1", symptoms=["diarrhoea"], dlat=0.003, hours_ago=12),
            report("R2", symptoms=["watery dung"], dlat=0.006, hours_ago=24),
            report("R3", symptoms=["scours"], dlat=0.009, hours_ago=36),
        ]
        result = pipeline.sweep(reports, now=NOW)
        assert len(result.clusters) == 1
        assert set(result.clusters[0].point_ids) == {"R0", "R1", "R2", "R3"}

    def test_sweep_output_is_json_serialisable(self, pipeline):
        import json

        reports = [report(f"R{i}", hours_ago=i * 12, dlat=0.004 * i) for i in range(4)]
        payload = pipeline.sweep(reports, now=NOW).to_dict()
        text = json.dumps(payload)
        json.loads(
            text, parse_constant=lambda c: pytest.fail(f"non-JSON constant emitted: {c}")
        )

    def test_empty_input_produces_no_alerts(self, pipeline):
        result = pipeline.sweep([], now=NOW)
        assert result.assessments == []
        assert result.clusters == []
        assert result.alerts == []

    def test_cluster_context_is_available_for_rescoring(self, pipeline):
        """A report inside a live cluster scores above the same report alone --
        this is the feedback loop from surveillance back into triage."""
        alone = pipeline.triage(report("R1", herd_size=10))
        in_cluster = pipeline.triage(
            Observation(
                report_id="R1", species="cattle", reported_at=NOW,
                symptoms=["fever", "cough"], herd_size=10, in_active_cluster=True,
            )
        )
        assert in_cluster.score > alone.score
        assert in_cluster.band.rank >= alone.band.rank
