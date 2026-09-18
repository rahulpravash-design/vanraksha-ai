from datetime import datetime, timedelta

import pytest

from app.models import Alert, Cluster, ClusterStatus

from .conftest import auth_headers, report_payload


@pytest.fixture
def outbreak(client, farmer_headers, farm):
    """Six related respiratory reports from nearby farms over ten days.

    Individually unremarkable; together they are the event the platform exists
    to surface.
    """
    now = datetime.utcnow()
    # The fourth report is the animal that got bad enough to need a vet, which
    # is what an outbreak looks like: mostly mild reports with a worsening tail.
    profile = [
        (9, ["fever", "nasal_discharge"], 0.000, None, 1),
        (7, ["fever", "cough"], 0.004, None, 1),
        (5, ["fever", "cough", "nasal_discharge"], 0.008, None, 2),
        (3, ["cough", "dyspnoea"], 0.006, 40.8, 4),
        (2, ["fever", "cough"], 0.010, None, 2),
        (1, ["fever", "nasal_discharge"], 0.012, None, 1),
    ]
    for index, (days_ago, symptoms, offset, temperature, affected) in enumerate(profile):
        payload = report_payload(
            f"outbreak-{index:04d}",
            farm_id=farm.id,
            symptoms=symptoms,
            reported_at=(now - timedelta(days=days_ago)).isoformat(),
            latitude=13.1667 + offset,
            longitude=77.8500 + offset,
            affected_count=affected,
        )
        if temperature is not None:
            payload["temperature_c"] = temperature
        response = client.post("/api/v1/reports", json=payload, headers=farmer_headers)
        assert response.status_code == 201, response.text
    return profile


class TestSweep:
    def test_related_reports_become_a_cluster(self, client, admin_headers, outbreak, db):
        response = client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["clusters_detected"] == 1

        cluster = db.query(Cluster).one()
        assert cluster.report_count == 6
        assert cluster.dominant_syndrome in ("respiratory", "systemic")
        assert cluster.explanation.endswith(".")
        assert cluster.villages == ["Sulibele"]

    def test_scattered_reports_produce_no_cluster(
        self, client, admin_headers, farmer_headers, farm, db
    ):
        """A false cluster costs a veterinary team a wasted field visit."""
        now = datetime.utcnow()
        for index, (symptom, offset) in enumerate(
            [("lameness", 0.5), ("milk_drop", 1.1), ("ectoparasites", 1.8)]
        ):
            client.post(
                "/api/v1/reports",
                json=report_payload(
                    f"scattered-{index:04d}", farm_id=farm.id, symptoms=[symptom],
                    reported_at=(now - timedelta(days=index * 9)).isoformat(),
                    latitude=13.1667 + offset, longitude=77.8500 + offset,
                ),
                headers=farmer_headers,
            )
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        assert db.query(Cluster).count() == 0

    def test_the_sweep_is_idempotent(self, client, admin_headers, outbreak, db):
        """A retried sweep must not produce a duplicate alert storm."""
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)

        assert db.query(Cluster).count() == 1
        assert db.query(Alert).filter(Alert.kind == "cluster").count() == 1

    def test_a_dismissed_cluster_stays_dismissed(
        self, client, admin_headers, vet_headers, outbreak, db
    ):
        """Re-raising a cluster a reviewer rejected is how a surveillance system
        trains its users to ignore it."""
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        cluster_id = db.query(Cluster).one().id

        client.post(
            f"/api/v1/clusters/{cluster_id}/review",
            json={"outcome": "dismissed", "notes": "Seasonal dust, not infectious."},
            headers=vet_headers,
        )
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)

        db.expire_all()
        assert db.get(Cluster, cluster_id).status is ClusterStatus.DISMISSED

    def test_only_administrators_can_run_a_sweep(self, client, farmer_headers, vet_headers):
        assert client.post(
            "/api/v1/surveillance/sweep", headers=farmer_headers
        ).status_code == 403
        assert client.post(
            "/api/v1/surveillance/sweep", headers=vet_headers
        ).status_code == 403

    def test_cases_are_linked_to_their_cluster(self, client, admin_headers, outbreak, db):
        """A vet opening one case has to be able to see it is part of an event."""
        from app.models import Case

        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        cluster = db.query(Cluster).one()
        linked = db.query(Case).filter(Case.cluster_id == cluster.id).all()
        assert linked, "no case was linked to the detected cluster"


class TestReview:
    def test_a_reviewer_verdict_is_recorded_as_ground_truth(
        self, client, admin_headers, vet_headers, vet, outbreak, db
    ):
        """Without the verdict there is no way to measure alert precision."""
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        cluster_id = db.query(Cluster).one().id

        response = client.post(
            f"/api/v1/clusters/{cluster_id}/review",
            json={"outcome": "confirmed", "notes": "Visited; consistent with the reports."},
            headers=vet_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["review_outcome"] == "confirmed"
        assert body["status"] == "confirmed"

        db.expire_all()
        assert db.get(Cluster, cluster_id).reviewed_by == vet.id

    def test_an_invalid_verdict_is_rejected(
        self, client, admin_headers, vet_headers, outbreak, db
    ):
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        cluster_id = db.query(Cluster).one().id
        response = client.post(
            f"/api/v1/clusters/{cluster_id}/review",
            json={"outcome": "probably-fine"}, headers=vet_headers,
        )
        assert response.status_code == 422

    def test_a_farmer_cannot_review_clusters(
        self, client, admin_headers, farmer_headers, outbreak, db
    ):
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        cluster_id = db.query(Cluster).one().id
        response = client.post(
            f"/api/v1/clusters/{cluster_id}/review",
            json={"outcome": "confirmed"}, headers=farmer_headers,
        )
        assert response.status_code == 403


class TestAlerts:
    def test_alerts_reach_the_roles_they_are_addressed_to(
        self, client, admin_headers, vet_headers, farmer_headers, outbreak
    ):
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)

        vet_alerts = client.get("/api/v1/alerts", headers=vet_headers).json()
        farmer_alerts = client.get("/api/v1/alerts", headers=farmer_headers).json()

        assert len(vet_alerts) >= 1
        # A cluster alert is operational; it is not routed to farmers.
        assert farmer_alerts == []

    def test_acknowledging_an_alert(self, client, admin_headers, vet_headers, vet, outbreak):
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        alert_id = client.get("/api/v1/alerts", headers=vet_headers).json()[0]["id"]

        response = client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge", headers=vet_headers
        )
        assert response.status_code == 200
        assert response.json()["acknowledged_by"] == vet.id

        remaining = client.get(
            "/api/v1/alerts?unacknowledged_only=true", headers=vet_headers
        ).json()
        assert all(a["id"] != alert_id for a in remaining)

    def test_a_user_cannot_acknowledge_an_alert_for_another_role(
        self, client, admin_headers, vet_headers, farmer_headers, outbreak
    ):
        client.post("/api/v1/surveillance/sweep", headers=admin_headers)
        alert_id = client.get("/api/v1/alerts", headers=vet_headers).json()[0]["id"]
        response = client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge", headers=farmer_headers
        )
        assert response.status_code in (403, 404)
