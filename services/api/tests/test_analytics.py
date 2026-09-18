from datetime import datetime, timedelta

from .conftest import auth_headers, report_payload


def _file(client, headers, farm, uuid, **kwargs):
    response = client.post(
        "/api/v1/reports", json=report_payload(uuid, farm_id=farm.id, **kwargs), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestSummary:
    def test_headline_figures(self, client, farmer_headers, farm):
        now = datetime.utcnow()
        for index in range(4):
            _file(
                client, farmer_headers, farm, f"summary-{index:04d}",
                reported_at=(now - timedelta(days=index)).isoformat(),
                affected_count=2,
            )
        body = client.get("/api/v1/analytics/summary", headers=farmer_headers).json()

        assert body["report_count"] == 4
        assert body["animal_count"] == 8
        assert body["weekly_series"]
        assert body["trend"]
        assert sum(body["band_counts"].values()) == 4

    def test_the_previous_period_is_included_for_comparison(
        self, client, farmer_headers, farm
    ):
        now = datetime.utcnow()
        _file(client, farmer_headers, farm, "period-0001",
              reported_at=(now - timedelta(days=2)).isoformat())
        _file(client, farmer_headers, farm, "period-0002",
              reported_at=(now - timedelta(days=40)).isoformat())

        body = client.get(
            "/api/v1/analytics/summary?days=30", headers=farmer_headers
        ).json()
        assert body["report_count"] == 1
        assert body["previous_period_count"] == 1

    def test_a_farmer_sees_only_their_own_figures(
        self, client, farmer_headers, farm, other_farmer
    ):
        _file(client, farmer_headers, farm, "scope-0001")
        theirs = client.get(
            "/api/v1/analytics/summary", headers=auth_headers(client, other_farmer.email)
        ).json()
        assert theirs["report_count"] == 0

    def test_an_administrator_sees_the_district(
        self, client, farmer_headers, admin_headers, farm
    ):
        _file(client, farmer_headers, farm, "scope-0002")
        body = client.get("/api/v1/analytics/summary", headers=admin_headers).json()
        assert body["report_count"] == 1
        assert "district" in body["scope"].lower()


class TestVillageBreakdown:
    def test_village_rows_carry_coordinates_for_the_map(
        self, client, farmer_headers, admin_headers, farm, village
    ):
        _file(client, farmer_headers, farm, "village-0001", deaths_count=0)
        rows = client.get("/api/v1/analytics/villages", headers=admin_headers).json()
        row = next(r for r in rows if r["village_id"] == village.id)
        assert row["report_count"] == 1
        assert row["latitude"] == village.latitude
        assert row["name"] == "Sulibele"


class TestPerformance:
    def test_operational_kpis_are_computed_from_timestamps(
        self, client, farmer_headers, vet_headers, farm
    ):
        _file(client, farmer_headers, farm, "perf-0001", symptoms=["mouth ulcer"])
        case_id = client.get("/api/v1/cases/queue", headers=vet_headers).json()[0]["id"]
        client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "resolved", "outcome": "recovered"},
            headers=vet_headers,
        )

        body = client.get("/api/v1/analytics/performance", headers=vet_headers).json()
        assert body["reports"] == 1
        assert body["cases"] == 1
        assert body["median_resolution_hours"] is not None
        assert body["data_completeness"] is not None

    def test_no_data_returns_nulls_rather_than_fabricated_zeros(
        self, client, vet_headers
    ):
        """A median of 'no cases' is not zero hours; saying so would be a lie
        on a dashboard someone makes decisions from."""
        body = client.get("/api/v1/analytics/performance", headers=vet_headers).json()
        assert body["reports"] == 0
        assert body["median_resolution_hours"] is None
        assert body["sla_met_rate"] is None

    def test_a_farmer_cannot_read_operational_kpis(self, client, farmer_headers):
        assert client.get(
            "/api/v1/analytics/performance", headers=farmer_headers
        ).status_code == 403


class TestVaccinationCoverage:
    def test_coverage_counts_never_covered_and_overdue(
        self, client, db, farmer_headers, field_worker, farm
    ):
        from app.models import Animal, Vaccination

        now = datetime.utcnow()
        animals = [Animal(tag=f"V-{i}", species="cattle", farm_id=farm.id) for i in range(3)]
        db.add_all(animals)
        db.commit()

        db.add(Vaccination(
            animal_id=animals[0].id, vaccine="FMD",
            administered_on=now - timedelta(days=30),
            next_due_on=now + timedelta(days=150),
        ))
        db.add(Vaccination(
            animal_id=animals[1].id, vaccine="FMD",
            administered_on=now - timedelta(days=400),
            next_due_on=now - timedelta(days=40),
        ))
        db.commit()

        body = client.get(
            "/api/v1/analytics/vaccination-coverage", headers=farmer_headers
        ).json()
        assert body["animals"] == 3
        assert body["covered"] == 1
        assert body["overdue"] == 1
        assert body["never"] == 1
        assert body["coverage_rate"] == round(1 / 3, 3)


class TestAssistant:
    def test_it_answers_from_the_records(self, client, farmer_headers, farm):
        for index in range(3):
            _file(client, farmer_headers, farm, f"assist-{index:04d}")

        response = client.post(
            "/api/v1/analytics/assistant",
            json={"question": "What changed this month?"},
            headers=farmer_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert "3 health report" in body["answer"]
        assert "not a diagnosis" in body["answer"]

    def test_a_diagnosis_request_is_redirected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/analytics/assistant",
            json={"question": "What disease does my cow have?"},
            headers=farmer_headers,
        )
        body = response.json()
        assert body["guardrail"] == "diagnosis_request"
        assert body["source"] == "guardrail"
        assert "can't name a disease" in body["answer"]

    def test_a_prescription_request_is_redirected(self, client, farmer_headers, farm):
        response = client.post(
            "/api/v1/analytics/assistant",
            json={"question": "How much ml of antibiotic should I give?"},
            headers=farmer_headers,
        )
        body = response.json()
        assert body["guardrail"] == "prescription_request"
        assert "can't recommend a medicine" in body["answer"]

    def test_the_answer_cannot_describe_records_the_caller_cannot_see(
        self, client, farmer_headers, farm, other_farmer
    ):
        """The context is built from the caller's own scoped aggregates, so it
        cannot leak another farmer's data through the assistant."""
        for index in range(5):
            _file(client, farmer_headers, farm, f"leak-{index:04d}")

        response = client.post(
            "/api/v1/analytics/assistant",
            json={"question": "Summarise the situation"},
            headers=auth_headers(client, other_farmer.email),
        )
        body = response.json()
        assert "5" not in body["answer"]
        assert "No health reports" in body["answer"]

    def test_the_assistant_requires_authentication(self, client):
        response = client.post(
            "/api/v1/analytics/assistant", json={"question": "Summarise"}
        )
        assert response.status_code == 401
