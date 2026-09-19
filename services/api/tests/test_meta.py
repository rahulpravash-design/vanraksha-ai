"""Service-level behaviour: health, docs, error shape, and the demo dataset."""

from app.models import Case, Cluster, HealthReport, RiskAssessmentRecord


class TestMeta:
    def test_health_endpoint(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["version"]

    def test_root_states_the_scope_of_the_system(self, client):
        """Anyone landing on the API must be told what it does not do."""
        notice = client.get("/").json()["notice"].lower()
        assert "not a diagnostic" in notice

    def test_openapi_document_builds(self, client):
        spec = client.get("/api/v1/openapi.json").json()
        assert spec["info"]["title"] == "VANRAKSHA AI"
        assert len(spec["paths"]) > 25

    def test_every_response_carries_a_request_id(self, client):
        """Field devices retry on flaky links; the request id is what makes a
        farmer's 'it did not appear' traceable."""
        response = client.get("/health")
        assert response.headers["X-Request-ID"]
        assert response.headers["X-Response-Time-ms"]

    def test_a_supplied_request_id_is_echoed(self, client):
        response = client.get("/health", headers={"X-Request-ID": "trace-me-123"})
        assert response.headers["X-Request-ID"] == "trace-me-123"


class TestSeed:
    def test_the_demo_dataset_produces_a_working_district(self, client, db):
        """The seed is the demo. If it stops generating a detectable event, the
        walkthrough silently becomes a tour of an empty dashboard."""
        from app.seed import DEFAULT_PASSWORD, seed

        result = seed(db, days=60)
        assert result["status"] == "seeded"
        assert "synthetic" in result["note"].lower()

        assert db.query(HealthReport).count() > 50
        # Every report must have been triaged.
        assert db.query(RiskAssessmentRecord).count() == db.query(HealthReport).count()
        assert db.query(Case).count() > 0

        # The seed provisions its own district administrator.
        token = client.post("/api/v1/auth/login", data={
            "username": "district@example.org", "password": DEFAULT_PASSWORD,
        }).json()["access_token"]
        sweep = client.post(
            "/api/v1/surveillance/sweep?window_days=21",
            headers={"Authorization": f"Bearer {token}"},
        ).json()

        assert sweep["clusters_detected"] >= 1, "the injected outbreak was not detected"
        assert db.query(Cluster).count() >= 1

    def test_seeding_a_populated_database_is_refused(self, db):
        from app.seed import seed

        seed(db, days=20)
        assert seed(db, days=20)["status"] == "skipped"

    def test_the_dataset_is_reproducible(self, db):
        """A demo that shuffles between runs cannot be rehearsed, and a changed
        cluster count stops being a signal that detection regressed."""
        from app.db import Base, engine
        from app.seed import seed

        first = seed(db, seed_value=99, days=30)

        db.close()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        second = seed(db, seed_value=99, days=30)
        assert first["reports"] == second["reports"]
        assert first["animals"] == second["animals"]
        assert first["farms"] == second["farms"]


class TestCors:
    def test_both_loopback_spellings_are_allowed_in_development(self, client):
        """A browser treats localhost and 127.0.0.1 as different origins; a
        default carrying only one of them breaks depending on which URL the
        developer typed."""
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            response = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert response.headers.get("access-control-allow-origin") == origin, origin

    def test_an_unlisted_origin_is_not_granted_access(self, client):
        response = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers.get("access-control-allow-origin") is None


class TestSeedRealism:
    def test_older_cases_carry_a_veterinary_history(self, db):
        """Without worked cases the response-performance panel has nothing to
        measure, and the demo silently claims a capability it cannot show."""
        from app.models import Case, CaseStatus
        from app.seed import seed

        result = seed(db, days=90)
        assert result["cases_worked"] > 0

        cases = db.query(Case).all()
        closed = [c for c in cases if c.closed_at is not None]
        assert closed, "no case reached a recorded outcome"

        for case in closed:
            assert case.assigned_at >= case.opened_at
            assert case.closed_at > case.assigned_at
            assert case.outcome

        # A live queue still has open work in it.
        assert any(
            c.status not in (CaseStatus.RESOLVED, CaseStatus.CLOSED) for c in cases
        )
