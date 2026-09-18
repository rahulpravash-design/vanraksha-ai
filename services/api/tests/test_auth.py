from app.models import Role, User

from .conftest import PASSWORD, auth_headers


class TestRegistration:
    def test_a_farmer_can_register_and_sign_in(self, client):
        response = client.post("/api/v1/auth/register", json={
            "email": "new.farmer@example.org",
            "password": "AStrongPassword1",
            "full_name": "New Farmer",
        })
        assert response.status_code == 201
        assert response.json()["role"] == "farmer"

        login = client.post("/api/v1/auth/login", data={
            "username": "new.farmer@example.org", "password": "AStrongPassword1",
        })
        assert login.status_code == 200
        assert login.json()["token_type"] == "bearer"

    def test_self_registration_cannot_claim_a_staff_role(self, client):
        """Otherwise anyone could sign up as a district officer and read every
        farmer's records."""
        for role in ("veterinarian", "district_admin", "super_admin", "field_worker"):
            response = client.post("/api/v1/auth/register", json={
                "email": f"{role}@attacker.example",
                "password": "AStrongPassword1",
                "full_name": "Attacker",
                "role": role,
            })
            assert response.status_code == 403, role

    def test_duplicate_registration_does_not_echo_the_address(self, client, farmer):
        """The message must not confirm the address is registered.

        The status code still differs from a successful registration, so this
        narrows enumeration rather than closing it -- the full fix is a
        confirm-by-email flow, tracked in docs/09-security/threat-model.md.
        """
        response = client.post("/api/v1/auth/register", json={
            "email": farmer.email, "password": "AStrongPassword1",
            "full_name": "Duplicate Attempt",
        })
        assert response.status_code == 400
        assert farmer.email not in response.json()["detail"]
        assert "already" not in response.json()["detail"].lower()

    def test_weak_passwords_are_rejected(self, client):
        response = client.post("/api/v1/auth/register", json={
            "email": "weak@example.org", "password": "short", "full_name": "Weak",
        })
        assert response.status_code == 422

    def test_email_is_normalised_to_lowercase(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "MixedCase@Example.org", "password": "AStrongPassword1",
            "full_name": "Mixed",
        })
        login = client.post("/api/v1/auth/login", data={
            "username": "mixedcase@example.org", "password": "AStrongPassword1",
        })
        assert login.status_code == 200


class TestLogin:
    def test_wrong_password_is_rejected(self, client, farmer):
        response = client.post("/api/v1/auth/login", data={
            "username": farmer.email, "password": "not-the-password",
        })
        assert response.status_code == 401

    def test_unknown_user_gets_the_same_error_as_a_wrong_password(self, client, farmer):
        unknown = client.post("/api/v1/auth/login", data={
            "username": "nobody@example.org", "password": PASSWORD,
        })
        wrong = client.post("/api/v1/auth/login", data={
            "username": farmer.email, "password": "wrong",
        })
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_a_disabled_account_cannot_sign_in(self, client, db, farmer):
        farmer.is_active = False
        db.commit()
        response = client.post("/api/v1/auth/login", data={
            "username": farmer.email, "password": PASSWORD,
        })
        assert response.status_code == 403


class TestTokens:
    def test_me_returns_the_signed_in_user(self, client, farmer, farmer_headers):
        response = client.get("/api/v1/auth/me", headers=farmer_headers)
        assert response.status_code == 200
        assert response.json()["email"] == farmer.email

    def test_no_token_is_unauthorised(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_a_garbage_token_is_unauthorised(self, client):
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"}
        )
        assert response.status_code == 401

    def test_a_token_for_a_deleted_user_is_rejected(self, client, db, farmer):
        headers = auth_headers(client, farmer.email)
        db.delete(db.get(User, farmer.id))
        db.commit()
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    def test_a_token_for_a_disabled_user_stops_working(self, client, db, farmer):
        headers = auth_headers(client, farmer.email)
        db.get(User, farmer.id).is_active = False
        db.commit()
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 403
