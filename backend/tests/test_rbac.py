"""Role-based access control: the core gap this work closed."""
from tests.conftest import auth


def test_admin_endpoints_reject_anonymous(client):
    for path in ("/api/admin/dashboard", "/api/admin/matches", "/api/admin/fb/sightings"):
        assert client.get(path).status_code == 401, path


def test_admin_endpoints_reject_normal_user(client, user_token):
    for path in ("/api/admin/dashboard", "/api/admin/matches", "/api/admin/fb/sightings"):
        res = client.get(path, headers=auth(user_token))
        assert res.status_code == 403, path


def test_admin_endpoints_allow_admin(client, admin_token):
    res = client.get("/api/admin/dashboard", headers=auth(admin_token))
    assert res.status_code == 200
    body = res.get_json()
    assert set(["total_cases", "active_cases", "pending_matches"]).issubset(body)


def test_stream_feed_requires_admin(client, user_token):
    assert client.get("/api/stream/feed").status_code == 401
    assert client.get("/api/stream/feed", headers=auth(user_token)).status_code == 403


def test_fb_scan_requires_admin(client, user_token):
    assert client.post("/api/admin/fb/scan", json={"demo": True}).status_code == 401
    res = client.post("/api/admin/fb/scan", json={"demo": True}, headers=auth(user_token))
    assert res.status_code == 403
