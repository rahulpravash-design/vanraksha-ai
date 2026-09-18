from datetime import datetime, timedelta

import pytest

from vanraksha_ai.clustering import (
    ClusterConfig,
    ClusterPoint,
    GeoTemporalClusterDetector,
    bounding_radius_km,
    centroid,
    detect_clusters,
    haversine_km,
    jaccard,
)

BASE = datetime(2026, 3, 1, 8, 0)


def point(pid, dlat=0.0, dlon=0.0, hours=0, symptoms=("fever", "cough"), **kwargs):
    return ClusterPoint(
        report_id=pid,
        latitude=12.90 + dlat,
        longitude=77.60 + dlon,
        observed_at=BASE + timedelta(hours=hours),
        symptom_codes=list(symptoms),
        village_id=kwargs.pop("village_id", "V-Alpha"),
        **kwargs,
    )


class TestGeometry:
    def test_haversine_against_a_known_distance(self):
        # Bengaluru to Chennai is roughly 290 km.
        assert haversine_km(12.9716, 77.5946, 13.0827, 80.2707) == pytest.approx(290, abs=8)

    def test_haversine_is_zero_for_identical_points(self):
        assert haversine_km(12.9, 77.6, 12.9, 77.6) == 0.0

    def test_haversine_is_symmetric(self):
        a = haversine_km(12.9, 77.6, 13.1, 77.9)
        b = haversine_km(13.1, 77.9, 12.9, 77.6)
        assert a == pytest.approx(b)

    def test_centroid_of_symmetric_points(self):
        lat, lon = centroid([(0.0, 0.0), (0.0, 2.0), (2.0, 0.0), (2.0, 2.0)])
        assert lat == pytest.approx(1.0, abs=0.01)
        assert lon == pytest.approx(1.0, abs=0.01)

    def test_centroid_handles_the_antimeridian(self):
        """Averaging degrees would put this in the middle of the wrong ocean."""
        lat, lon = centroid([(0.0, 179.0), (0.0, -179.0)])
        assert abs(lon) == pytest.approx(180.0, abs=0.01)

    def test_bounding_radius(self):
        points = [(12.90, 77.60), (12.95, 77.60)]
        assert bounding_radius_km(points) == pytest.approx(2.78, abs=0.2)

    def test_jaccard(self):
        assert jaccard(["a", "b"], ["a", "b"]) == 1.0
        assert jaccard(["a"], ["b"]) == 0.0
        assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
        assert jaccard([], []) == 1.0


class TestDetection:
    def test_a_real_cluster_is_found(self):
        points = [point(f"R{i}", dlat=0.004 * i, hours=12 * i) for i in range(5)]
        clusters = detect_clusters(points)
        assert len(clusters) == 1
        assert clusters[0].report_count == 5

    def test_scattered_reports_produce_nothing(self):
        points = [point(f"R{i}", dlat=0.9 * i, dlon=0.9 * i, hours=200 * i) for i in range(6)]
        assert detect_clusters(points) == []

    def test_distant_noise_is_excluded_from_a_real_cluster(self):
        points = [point(f"R{i}", dlat=0.004 * i, hours=10 * i) for i in range(4)]
        points.append(point("FAR", dlat=3.0, dlon=3.0, hours=5))
        clusters = detect_clusters(points)
        assert len(clusters) == 1
        assert "FAR" not in clusters[0].point_ids

    def test_time_separation_splits_a_cluster(self):
        """Same place, months apart, is two events -- not one long one."""
        near = [point(f"A{i}", dlat=0.002 * i, hours=6 * i) for i in range(4)]
        later = [point(f"B{i}", dlat=0.002 * i, hours=2000 + 6 * i) for i in range(4)]
        clusters = detect_clusters(near + later)
        assert len(clusters) == 2

    def test_different_syndromes_do_not_merge(self):
        respiratory = [
            point(f"RESP{i}", dlat=0.002 * i, hours=6 * i, symptoms=("fever", "cough"))
            for i in range(4)
        ]
        lameness = [
            point(f"LAME{i}", dlat=0.002 * i, hours=6 * i + 2, symptoms=("lameness",))
            for i in range(4)
        ]
        clusters = detect_clusters(respiratory + lameness)
        for cluster in clusters:
            prefixes = {pid[:4] for pid in cluster.point_ids}
            assert len(prefixes) == 1, "unrelated syndromes were merged"

    def test_species_groups_are_kept_apart(self):
        bovine = [
            point(f"C{i}", dlat=0.002 * i, hours=6 * i, species="cattle", species_group="bovine")
            for i in range(3)
        ]
        avian = [
            point(f"P{i}", dlat=0.002 * i, hours=6 * i, species="poultry", species_group="avian")
            for i in range(3)
        ]
        for cluster in detect_clusters(bovine + avian):
            assert len({cluster_species for cluster_species in cluster.species}) == 1

    def test_species_separation_can_be_disabled(self):
        config = ClusterConfig(respect_species_group=False)
        mixed = [
            point("C1", species="cattle", species_group="bovine"),
            point("G1", dlat=0.002, hours=4, species="goat", species_group="small_ruminant"),
            point("S1", dlat=0.004, hours=8, species="sheep", species_group="small_ruminant"),
        ]
        clusters = detect_clusters(mixed, config)
        assert len(clusters) == 1
        assert len(clusters[0].species) == 3

    def test_min_reports_is_respected(self):
        two = [point("R0"), point("R1", dlat=0.002, hours=4)]
        assert detect_clusters(two) == []
        assert len(detect_clusters(two, ClusterConfig(min_reports=2))) == 1

    def test_below_minimum_input_returns_empty(self):
        assert detect_clusters([point("R0")]) == []
        assert detect_clusters([]) == []

    def test_neighbour_predicate_requires_all_three_conditions(self):
        detector = GeoTemporalClusterDetector(ClusterConfig(radius_km=5, window_hours=48))
        anchor = point("A")
        assert detector.is_neighbour(anchor, point("B", dlat=0.01, hours=6))
        assert not detector.is_neighbour(anchor, point("C", dlat=1.0, hours=6))       # too far
        assert not detector.is_neighbour(anchor, point("D", dlat=0.01, hours=500))    # too old
        assert not detector.is_neighbour(
            anchor, point("E", dlat=0.01, hours=6, symptoms=("lameness",))            # unrelated
        )


class TestSummary:
    def test_summary_fields(self):
        points = [
            point("R0", deaths_count=1, risk_score=60, affected_count=2),
            point("R1", dlat=0.004, hours=12, risk_score=40),
            point("R2", dlat=0.008, hours=24, village_id="V-Beta", risk_score=50),
            point("R3", dlat=0.006, hours=30, village_id="V-Beta", risk_score=55),
        ]
        cluster = detect_clusters(points)[0]
        assert cluster.report_count == 4
        assert cluster.death_count == 1
        assert cluster.animal_count == 5
        assert cluster.villages == ["V-Alpha", "V-Beta"]
        assert cluster.dominant_syndrome in ("respiratory", "systemic")
        assert 0 <= cluster.severity_score <= 100
        assert cluster.mean_risk_score == pytest.approx(51.25)
        assert cluster.explanation.endswith(".")

    def test_growth_ratio_detects_acceleration(self):
        # Three reports early, five bunched at the end.
        early = [point(f"E{i}", dlat=0.001 * i, hours=i * 3) for i in range(3)]
        late = [point(f"L{i}", dlat=0.001 * i, hours=90 + i) for i in range(5)]
        cluster = detect_clusters(early + late)[0]
        assert cluster.growth_ratio > 1.5

    def test_deaths_push_severity_up(self):
        quiet = [point(f"Q{i}", dlat=0.002 * i, hours=8 * i) for i in range(4)]
        fatal = [
            point(f"F{i}", dlat=0.002 * i, hours=8 * i, deaths_count=1) for i in range(4)
        ]
        assert detect_clusters(fatal)[0].severity_score > detect_clusters(quiet)[0].severity_score

    def test_clusters_are_ordered_by_severity(self):
        small = [point(f"S{i}", dlat=0.002 * i, hours=6 * i) for i in range(3)]
        big = [
            point(f"B{i}", dlat=2.0 + 0.002 * i, hours=6 * i, deaths_count=1, village_id="V-Big")
            for i in range(6)
        ]
        clusters = detect_clusters(small + big)
        assert len(clusters) == 2
        assert clusters[0].severity_score >= clusters[1].severity_score
        assert clusters[0].cluster_id == "CL-001"

    def test_serialisation_is_json_safe(self):
        import json

        points = [point(f"R{i}", dlat=0.002 * i, hours=6 * i) for i in range(4)]
        payload = detect_clusters(points)[0].to_dict()
        assert json.loads(json.dumps(payload))["report_count"] == 4
