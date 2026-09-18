"""Test fixtures.

The database URL is set before any application module is imported, because
``app.db`` builds its engine at import time. An in-memory SQLite database with a
static pool gives every test a real schema with no files to clean up.
"""

from __future__ import annotations

import os

os.environ.setdefault("VANRAKSHA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("VANRAKSHA_ENVIRONMENT", "test")

from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Farm, Role, User, Village  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "TestPassword2026!"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def village(db) -> Village:
    village = Village(
        name="Sulibele", block="Hoskote", district="Bengaluru Rural",
        state="Karnataka", latitude=13.1667, longitude=77.8500,
        livestock_population=1240,
    )
    db.add(village)
    db.commit()
    db.refresh(village)
    return village


def _make_user(db, email: str, role: Role, **kwargs) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(PASSWORD),
        full_name=email.split("@")[0].replace(".", " ").title(),
        role=role,
        **kwargs,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def farmer(db, village) -> User:
    return _make_user(
        db, "farmer@example.org", Role.FARMER,
        village_id=village.id, block=village.block, district=village.district,
    )


@pytest.fixture
def other_farmer(db, village) -> User:
    return _make_user(
        db, "other.farmer@example.org", Role.FARMER,
        village_id=village.id, block=village.block, district=village.district,
    )


@pytest.fixture
def vet(db, village) -> User:
    return _make_user(
        db, "vet@example.org", Role.VETERINARIAN,
        block=village.block, district=village.district,
    )


@pytest.fixture
def second_vet(db, village) -> User:
    return _make_user(
        db, "vet2@example.org", Role.VETERINARIAN,
        block=village.block, district=village.district,
    )


@pytest.fixture
def field_worker(db, village) -> User:
    return _make_user(
        db, "field@example.org", Role.FIELD_WORKER,
        block=village.block, district=village.district,
    )


@pytest.fixture
def district_admin(db, village) -> User:
    return _make_user(
        db, "district@example.org", Role.DISTRICT_ADMIN, district=village.district
    )


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def farmer_headers(client, farmer) -> dict[str, str]:
    return auth_headers(client, farmer.email)


@pytest.fixture
def vet_headers(client, vet) -> dict[str, str]:
    return auth_headers(client, vet.email)


@pytest.fixture
def admin_headers(client, district_admin) -> dict[str, str]:
    return auth_headers(client, district_admin.email)


@pytest.fixture
def farm(db, farmer, village) -> Farm:
    farm = Farm(
        name="Test holding", owner_id=farmer.id, village_id=village.id,
        latitude=village.latitude, longitude=village.longitude,
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


def report_payload(uuid: str, **overrides) -> dict:
    payload = {
        "client_uuid": uuid,
        "species": "cattle",
        "symptoms": ["fever", "cough"],
        "affected_count": 1,
        "latitude": 13.1667,
        "longitude": 77.8500,
    }
    payload.update(overrides)
    return payload


def iso(days_ago: float = 0, hours_ago: float = 0) -> str:
    return (
        datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)
    ).isoformat()
