from app.models import Case, HealthReport

from .conftest import iso, report_payload


class TestReporting:
    def test_filing_a_report_returns_the_triage_verdict_immediately(
        self, client, farmer_headers, farm
    ):
        """The field app has to be able to tell a farmer 'this needs a vet
        today' before they walk away from the animal."""
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-0001", farm_id=farm.id, temperature_c=40.6),
            headers=farmer_headers,
        )
        assert response.status_code == 201
        body = response.json()

        assert body["assessment"] is not None
        assert body["assessment"]["band"] in (
            "routine", "monitor", "priority", "urgent", "emergency"
        )
        assert body["assessment"]["recommended_action"]
        assert body["assessment"]["contributions"]

    def test_every_point_of_the_score_is_explained(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-0002", farm_id=farm.id, temperature_c=41.0),
            headers=farmer_headers,
        )
        assessment = response.json()["assessment"]
        for contribution in assessment["contributions"]:
            assert contribution["rule_id"]
            assert contribution["evidence"].strip()
        total = sum(c["points"] for c in assessment["contributions"])
        assert abs(min(100.0, total) - assessment["score"]) < 0.1

    def test_free_text_symptoms_are_normalised(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json=report_payload(
                "uuid-0003", farm_id=farm.id,
                symptoms=["not eating", "loose motion"], symptoms_text="also has a cough",
            ),
            headers=farmer_headers,
        )
        codes = response.json()["symptom_codes"]
        assert set(codes) >= {"reduced_appetite", "diarrhoea", "cough"}

    def test_unrecognised_text_is_kept_for_review_not_dropped(
        self, client, farmer_headers, farm
    ):
        response = client.post(
            "/api/v1/reports",
            json=report_payload(
                "uuid-0004", farm_id=farm.id,
                symptoms=["fever", "walking oddly sideways at dusk"],
            ),
            headers=farmer_headers,
        )
        assert response.json()["unmatched_terms"] == ["walking oddly sideways at dusk"]

    def test_farm_context_is_filled_in_from_the_animal(
        self, client, farmer_headers, farm, db
    ):
        from app.models import Animal

        animal = Animal(tag="A-01", species="cattle", farm_id=farm.id)
        db.add(animal)
        db.commit()

        response = client.post(
            "/api/v1/reports",
            json={
                "client_uuid": "uuid-0005", "species": "cattle",
                "symptoms": ["fever"], "animal_id": animal.id,
            },
            headers=farmer_headers,
        )
        body = response.json()
        assert body["farm_id"] == farm.id
        assert body["village_id"] == farm.village_id
        # Coordinates fall back to the farm when the device had no GPS fix.
        assert body["latitude"] == farm.latitude

    def test_a_report_without_a_location_is_still_accepted(
        self, client, farmer_headers
    ):
        response = client.post(
            "/api/v1/reports",
            json={"client_uuid": "uuid-0006", "species": "goat", "symptoms": ["fever"]},
            headers=farmer_headers,
        )
        assert response.status_code == 201
        assert response.json()["assessment"]["band"] is not None


class TestIdempotency:
    def test_resubmitting_the_same_client_uuid_does_not_duplicate(
        self, client, farmer_headers, farm, db
    ):
        """A device that retries after a dropped connection must not create a
        second report."""
        payload = report_payload("uuid-retry-0001", farm_id=farm.id)
        first = client.post("/api/v1/reports", json=payload, headers=farmer_headers)
        second = client.post("/api/v1/reports", json=payload, headers=farmer_headers)

        assert first.json()["id"] == second.json()["id"]
        assert db.query(HealthReport).count() == 1


class TestValidation:
    def test_more_affected_than_the_herd_holds_is_rejected(
        self, client, farmer_headers, farm
    ):
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-bad1", farm_id=farm.id, herd_size=10, affected_count=40),
            headers=farmer_headers,
        )
        assert response.status_code == 422
        assert any("herd_size" in e["message"] for e in response.json()["errors"])

    def test_more_deaths_than_affected_is_rejected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-bad2", farm_id=farm.id, affected_count=2, deaths_count=5),
            headers=farmer_headers,
        )
        assert response.status_code == 422

    def test_an_empty_report_is_rejected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json={"client_uuid": "uuid-bad3", "species": "cattle", "farm_id": farm.id},
            headers=farmer_headers,
        )
        assert response.status_code == 422

    def test_an_impossible_temperature_is_rejected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-bad4", farm_id=farm.id, temperature_c=88.0),
            headers=farmer_headers,
        )
        assert response.status_code == 422

    def test_a_future_date_is_rejected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-bad5", farm_id=farm.id, reported_at=iso(days_ago=-9)),
            headers=farmer_headers,
        )
        assert response.status_code == 422

    def test_validation_errors_name_the_field(self, client, farmer_headers, farm):
        """A farmer on a phone needs to know which box is wrong."""
        response = client.post(
            "/api/v1/reports",
            json=report_payload("uuid-bad6", farm_id=farm.id, species="unicorn"),
            headers=farmer_headers,
        )
        errors = response.json()["errors"]
        assert any(e["field"] == "species" for e in errors)


class TestOfflineSync:
    def test_a_queued_batch_is_drained(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/reports/sync",
            json={
                "device_id": "device-7",
                "reports": [
                    report_payload("queued-0001", farm_id=farm.id, reported_at=iso(days_ago=2)),
                    report_payload("queued-0002", farm_id=farm.id, reported_at=iso(days_ago=1)),
                    report_payload("queued-0003", farm_id=farm.id),
                ],
            },
            headers=farmer_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] == 3
        assert all(item["band"] for item in body["results"])

    def test_one_bad_item_does_not_cost_the_farmer_the_rest(
        self, client, farmer_headers, farm
    ):
        """The whole point of the offline queue is that a week of field work
        survives contact with the network."""
        response = client.post(
            "/api/v1/reports/sync",
            json={
                "reports": [
                    report_payload("mixed-0001", farm_id=farm.id),
                    report_payload("mixed-0002", farm_id="a-farm-that-does-not-exist"),
                    report_payload("mixed-0003", farm_id=farm.id),
                ]
            },
            headers=farmer_headers,
        )
        body = response.json()
        assert body["accepted"] == 2
        assert body["rejected"] == 1
        rejected = next(r for r in body["results"] if r["status"] == "rejected")
        assert rejected["client_uuid"] == "mixed-0002"
        assert rejected["detail"]

    def test_replaying_a_batch_reports_duplicates_rather_than_failing(
        self, client, farmer_headers, farm, db
    ):
        batch = {"reports": [report_payload("duplicate-0001", farm_id=farm.id)]}
        client.post("/api/v1/reports/sync", json=batch, headers=farmer_headers)
        second = client.post("/api/v1/reports/sync", json=batch, headers=farmer_headers)

        assert second.json()["duplicates"] == 1
        assert second.json()["accepted"] == 0
        assert db.query(HealthReport).count() == 1

    def test_synced_reports_are_flagged_as_offline(self, client, farmer_headers, farm, db):
        client.post(
            "/api/v1/reports/sync",
            json={"reports": [report_payload("offline-0001", farm_id=farm.id)]},
            headers=farmer_headers,
        )
        report = db.query(HealthReport).one()
        assert report.submitted_offline is True


class TestAccessControl:
    def test_a_farmer_cannot_report_on_another_farmer_s_animal(
        self, client, db, farm, other_farmer
    ):
        from .conftest import auth_headers

        headers = auth_headers(client, other_farmer.email)
        response = client.post(
            "/api/v1/reports",
            json=report_payload("intruder-0001", farm_id=farm.id),
            headers=headers,
        )
        assert response.status_code == 403

    def test_a_farmer_cannot_read_another_farmer_s_report(
        self, client, farmer_headers, farm, other_farmer
    ):
        from .conftest import auth_headers

        created = client.post(
            "/api/v1/reports",
            json=report_payload("private-0001", farm_id=farm.id),
            headers=farmer_headers,
        ).json()

        response = client.get(
            f"/api/v1/reports/{created['id']}",
            headers=auth_headers(client, other_farmer.email),
        )
        # 404 rather than 403: confirming the record exists is itself a disclosure.
        assert response.status_code == 404

    def test_a_vet_in_the_same_block_can_read_the_report(
        self, client, farmer_headers, vet_headers, farm
    ):
        created = client.post(
            "/api/v1/reports",
            json=report_payload("shared-0001", farm_id=farm.id),
            headers=farmer_headers,
        ).json()
        response = client.get(f"/api/v1/reports/{created['id']}", headers=vet_headers)
        assert response.status_code == 200

    def test_listing_is_scoped_to_the_caller(
        self, client, farmer_headers, farm, other_farmer
    ):
        from .conftest import auth_headers

        client.post(
            "/api/v1/reports",
            json=report_payload("scoped-0001", farm_id=farm.id),
            headers=farmer_headers,
        )
        mine = client.get("/api/v1/reports", headers=farmer_headers).json()
        theirs = client.get(
            "/api/v1/reports", headers=auth_headers(client, other_farmer.email)
        ).json()
        assert len(mine) == 1
        assert theirs == []

    def test_reporting_requires_authentication(self, client, farm):
        response = client.post(
            "/api/v1/reports", json=report_payload("anonymous-0001", farm_id=farm.id)
        )
        assert response.status_code == 401


class TestTaxonomyEndpoint:
    def test_the_field_app_can_fetch_the_vocabulary(self, client):
        response = client.get("/api/v1/reports/taxonomy")
        assert response.status_code == 200
        body = response.json()
        assert len(body["symptoms"]) > 20
        assert len(body["syndromes"]) > 5
        sample = body["symptoms"][0]
        assert {"code", "label", "syndromes", "severity_weight"} <= set(sample)


class TestCaseCreation:
    def test_an_escalated_report_opens_a_case_automatically(
        self, client, farmer_headers, farm, db
    ):
        client.post(
            "/api/v1/reports",
            json=report_payload(
                "casecheck-0001", farm_id=farm.id,
                symptoms=["mouth ulcer", "drooling"], affected_count=3,
            ),
            headers=farmer_headers,
        )
        case = db.query(Case).one()
        assert case.band in ("priority", "urgent", "emergency")
        assert case.due_at is not None

    def test_a_routine_report_does_not_open_a_case(
        self, client, farmer_headers, farm, db
    ):
        """Opening a case for every routine report buries the queue that the
        escalated ones depend on."""
        client.post(
            "/api/v1/reports",
            json=report_payload("casecheck-0002", farm_id=farm.id, symptoms=["ticks"]),
            headers=farmer_headers,
        )
        assert db.query(Case).count() == 0
