def test_login_success(client):
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": "password123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "customer@test.com"


def test_login_wrong_password(client):
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "password123"})
    assert res.status_code == 401


def test_login_invalid_email_format(client):
    res = client.post("/api/auth/login", json={"email": "not-an-email", "password": "password123"})
    assert res.status_code == 422


def test_login_empty_password(client):
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": ""})
    assert res.status_code == 422


def test_get_me_authenticated(client, customer_token):
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {customer_token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "customer@test.com"


def test_get_me_unauthenticated(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_get_me_invalid_token(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert res.status_code == 401


def test_register_new_user(client):
    res = client.post("/api/auth/register", json={
        "full_name": "New User",
        "email": "newuser@test.com",
        "password": "securepass123",
    })
    assert res.status_code == 200
    assert res.json()["user"]["email"] == "newuser@test.com"


def test_register_duplicate_email(client):
    res = client.post("/api/auth/register", json={
        "full_name": "Duplicate",
        "email": "customer@test.com",
        "password": "securepass123",
    })
    assert res.status_code == 400


def test_register_short_password(client):
    res = client.post("/api/auth/register", json={
        "full_name": "Short Pass",
        "email": "shortpass@test.com",
        "password": "123",
    })
    assert res.status_code == 422
