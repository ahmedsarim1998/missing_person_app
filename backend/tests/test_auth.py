from tests.conftest import auth


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_signup_validation(client):
    # too-short password
    res = client.post("/api/auth/signup", json={
        "username": "bob", "password": "short", "email": "bob@x.com",
        "first_name": "Bob", "last_name": "Jones",
    })
    assert res.status_code == 400

    # bad email
    res = client.post("/api/auth/signup", json={
        "username": "bob", "password": "password123", "email": "not-an-email",
        "first_name": "Bob", "last_name": "Jones",
    })
    assert res.status_code == 400


def test_signup_then_login(client):
    res = client.post("/api/auth/signup", json={
        "username": "alice", "password": "password123", "email": "alice@x.com",
        "first_name": "Alice", "last_name": "Smith",
    })
    assert res.status_code == 201

    # duplicate
    res = client.post("/api/auth/signup", json={
        "username": "alice", "password": "password123", "email": "alice@x.com",
        "first_name": "Alice", "last_name": "Smith",
    })
    assert res.status_code == 409

    res = client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["role"] == "user"
    assert body["access_token"]


def test_login_bad_password(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_signup_cannot_self_assign_admin(client):
    res = client.post("/api/auth/signup", json={
        "username": "sneaky", "password": "password123", "email": "sneaky@x.com",
        "first_name": "S", "last_name": "Neaky", "role": "admin",
    })
    assert res.status_code == 201
    login = client.post("/api/auth/login", json={"username": "sneaky", "password": "password123"})
    assert login.get_json()["role"] == "user"  # role field is ignored on signup


def test_me_requires_token(client, user_token):
    assert client.get("/api/auth/me").status_code == 401
    res = client.get("/api/auth/me", headers=auth(user_token))
    assert res.status_code == 200
    assert res.get_json()["role"] == "user"
