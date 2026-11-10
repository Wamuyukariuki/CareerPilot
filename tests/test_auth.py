def test_register_creates_three_independent_career_tracks(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "Person@example.com",
            "full_name": "  A Person  ",
            "password": "a-very-long-test-password",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "person@example.com"
    assert response.json()["full_name"] == "A Person"

    login_response = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "a-very-long-test-password"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    preferences = client.get(
        "/api/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert preferences.status_code == 200
    tracks = {item["track"] for item in preferences.json()}
    assert tracks == {
        "software_engineering",
        "cybersecurity",
        "electrical_engineering",
    }
    assert all(item["target_titles"] for item in preferences.json())


def test_rejects_duplicate_registration_and_weak_password(client):
    payload = {
        "email": "person@example.com",
        "full_name": "A Person",
        "password": "a-very-long-test-password",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409
    payload["email"] = "another@example.com"
    payload["password"] = "short"
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_protected_route_requires_valid_access_token(client):
    assert client.get("/api/auth/me").status_code == 401
    response = client.post(
        "/api/auth/register",
        json={
            "email": "person@example.com",
            "full_name": "A Person",
            "password": "a-very-long-test-password",
        },
    )
    assert response.status_code == 201
    token = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "a-very-long-test-password"},
    ).json()["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 401


def test_login_does_not_disclose_whether_email_exists(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "test-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
