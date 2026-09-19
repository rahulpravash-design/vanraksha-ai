from app.models import Case, CaseStatus

from .conftest import auth_headers, report_payload


def _file(client, headers, farm, uuid, **kwargs):
    return client.post(
        "/api/v1/reports", json=report_payload(uuid, farm_id=farm.id, **kwargs), headers=headers
    ).json()


class TestQueue:
    def test_the_queue_is_ordered_by_urgency_not_arrival(
        self, client, farmer_headers, vet_headers, farm
    ):
        """A queue sorted by arrival time is the paper system with extra steps."""
        _file(client, farmer_headers, farm, "queue-routine", symptoms=["laboured breathing"])
        _file(
            client, farmer_headers, farm, "queue-emergency",
            symptoms=["found dead", "blood from nose"], deaths_count=1,
        )
        _file(client, farmer_headers, farm, "queue-vesicular", symptoms=["mouth ulcer"])

        queue = client.get("/api/v1/cases/queue", headers=vet_headers).json()
        bands = [case["band"] for case in queue]
        order = {"priority": 2, "urgent": 3, "emergency": 4}
        assert bands[0] == "emergency"
        assert [order[b] for b in bands] == sorted([order[b] for b in bands], reverse=True)

    def test_a_farmer_cannot_open_the_veterinary_queue(self, client, farmer_headers):
        assert client.get("/api/v1/cases/queue", headers=farmer_headers).status_code == 403

    def test_mine_only_filters_to_the_signed_in_vet(
        self, client, farmer_headers, vet_headers, vet, farm
    ):
        _file(client, farmer_headers, farm, "mine-0001", symptoms=["mouth ulcer"])
        queue = client.get("/api/v1/cases/queue", headers=vet_headers).json()
        case_id = queue[0]["id"]

        assert client.get(
            "/api/v1/cases/queue?mine_only=true", headers=vet_headers
        ).json() == []

        client.post(
            f"/api/v1/cases/{case_id}/assign",
            json={"veterinarian_id": vet.id}, headers=vet_headers,
        )
        assert len(
            client.get("/api/v1/cases/queue?mine_only=true", headers=vet_headers).json()
        ) == 1

    def test_closed_cases_are_out_of_the_queue_by_default(
        self, client, farmer_headers, vet_headers, farm
    ):
        _file(client, farmer_headers, farm, "closed-0001", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "closed", "outcome": "recovered"}, headers=vet_headers,
        )
        assert client.get("/api/v1/cases/queue", headers=vet_headers).json() == []
        assert len(
            client.get("/api/v1/cases/queue?include_closed=true", headers=vet_headers).json()
        ) == 1


class TestAssignment:
    def test_assigning_records_the_timestamp(
        self, client, farmer_headers, vet_headers, vet, farm
    ):
        _file(client, farmer_headers, farm, "assign-0001", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        response = client.post(
            f"/api/v1/cases/{case_id}/assign",
            json={"veterinarian_id": vet.id}, headers=vet_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["assigned_vet_id"] == vet.id
        assert body["assigned_at"] is not None
        assert body["status"] == "assigned"

    def test_a_case_cannot_be_assigned_to_a_non_veterinarian(
        self, client, farmer_headers, vet_headers, farmer, farm
    ):
        _file(client, farmer_headers, farm, "assign-0002", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        response = client.post(
            f"/api/v1/cases/{case_id}/assign",
            json={"veterinarian_id": farmer.id}, headers=vet_headers,
        )
        assert response.status_code == 400

    def test_a_case_cannot_be_assigned_to_a_disabled_account(
        self, client, db, farmer_headers, vet_headers, second_vet, farm
    ):
        """Work must not be routed into a queue nobody can open."""
        _file(client, farmer_headers, farm, "assign-0003", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        second_vet.is_active = False
        db.commit()
        response = client.post(
            f"/api/v1/cases/{case_id}/assign",
            json={"veterinarian_id": second_vet.id}, headers=vet_headers,
        )
        assert response.status_code == 400


class TestProgression:
    def test_a_vet_can_close_a_case_with_an_outcome(
        self, client, farmer_headers, vet_headers, farm, db
    ):
        _file(client, farmer_headers, farm, "progress-0001", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        response = client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "resolved", "outcome": "recovered",
                  "resolution_notes": "Isolated; signs resolved in four days."},
            headers=vet_headers,
        )
        assert response.status_code == 200
        case = db.get(Case, case_id)
        assert case.status is CaseStatus.RESOLVED
        assert case.closed_at is not None
        assert case.first_response_at is not None

    def test_a_closed_case_cannot_be_reopened(
        self, client, farmer_headers, vet_headers, farm
    ):
        """Reopening would lose the audit boundary; a new report is the path."""
        _file(client, farmer_headers, farm, "progress-0002", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "closed"}, headers=vet_headers
        )
        response = client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "open"}, headers=vet_headers
        )
        assert response.status_code == 409

    def test_only_clinical_roles_can_advance_a_case(
        self, client, farmer_headers, vet_headers, field_worker, farm
    ):
        """A field worker can assign and triage but must not record a clinical
        outcome on a vet's behalf."""
        _file(client, farmer_headers, farm, "progress-0003", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]

        response = client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "resolved"},
            headers=auth_headers(client, field_worker.email),
        )
        assert response.status_code == 403

    def test_a_reassessment_that_raises_the_band_pulls_the_deadline_in(
        self, client, farmer_headers, farm, db
    ):
        from app.services.triage import assess_report
        from app.models import HealthReport

        _file(client, farmer_headers, farm, "reassess-0001", symptoms=["mouth ulcer"])
        case = db.query(Case).one()
        original_due = case.due_at

        report = db.query(HealthReport).one()
        report.symptoms_text = "now also found dead with blood from nose"
        report.deaths_count = 1
        assess_report(db, report)
        db.commit()
        db.refresh(case)

        assert case.band == "emergency"
        assert case.due_at < original_due


class TestCaseTimestamps:
    def test_a_case_opens_when_the_report_arrived_not_when_triage_ran(
        self, client, farmer_headers, farm, db
    ):
        """Stamping every case with the wall clock makes a backfill look like it
        all happened at once, and makes (assigned_at - opened_at) meaningless.

        For a live submission `received_at` is now, so the two coincide. The
        case that matters is a historical import, where they must not.
        """
        from datetime import datetime, timedelta

        from app.models import HealthReport
        from app.services.triage import assess_report

        _file(client, farmer_headers, farm, "backfill-0001", symptoms=["mouth ulcer"])

        # Re-stamp the report as a historical import and re-triage it, which is
        # what a backfill or a re-run of a tuned engine actually does.
        report = db.query(HealthReport).one()
        arrived = datetime.utcnow() - timedelta(days=9)
        report.reported_at = arrived - timedelta(hours=2)
        report.received_at = arrived
        db.query(Case).delete()
        db.commit()

        assess_report(db, report)
        db.commit()

        case = db.query(Case).one()
        assert case.opened_at == arrived
        assert (datetime.utcnow() - case.opened_at) > timedelta(days=8)
        # The deadline runs from the observation, so it has long passed.
        assert case.is_overdue

    def test_a_live_report_opens_its_case_now(self, client, farmer_headers, farm, db):
        from datetime import datetime, timedelta

        _file(client, farmer_headers, farm, "livecase-0001", symptoms=["mouth ulcer"])
        case = db.query(Case).one()
        assert (datetime.utcnow() - case.opened_at) < timedelta(minutes=5)
