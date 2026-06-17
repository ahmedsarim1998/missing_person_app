"""Admin review workflow + resolution audit trail."""
from tests.conftest import auth


def _make_alert(app):
    from extensions import db
    from models import MissingPerson, MatchAlert
    with app.app_context():
        person = MissingPerson(name="Audit Target", status="active")
        db.session.add(person)
        db.session.commit()
        alert = MatchAlert(missing_person_id=person.id, confidence=0.42, status="pending")
        db.session.add(alert)
        db.session.commit()
        return alert.id


def test_resolve_records_audit_trail(app, client, admin_token):
    alert_id = _make_alert(app)

    res = client.post("/api/admin/match/%d" % alert_id, json={"action": "confirm"},
                      headers=auth(admin_token))
    assert res.status_code == 200
    assert res.get_json()["status"] == "confirmed"

    from extensions import db
    from models import MatchAlert
    with app.app_context():
        alert = db.session.get(MatchAlert, alert_id)
        assert alert.status == "confirmed"
        assert alert.resolved_by == "admin"      # audit: who
        assert alert.resolved_at is not None      # audit: when


def test_resolve_rejects_invalid_action(app, client, admin_token):
    alert_id = _make_alert(app)
    res = client.post("/api/admin/match/%d" % alert_id, json={"action": "bogus"},
                      headers=auth(admin_token))
    assert res.status_code == 400


def test_fb_scan_demo_runs_for_admin(client, admin_token):
    res = client.post("/api/admin/fb/scan", json={"demo": True}, headers=auth(admin_token))
    assert res.status_code == 200
    body = res.get_json()
    assert set(["scanned", "matched", "updated", "skipped"]).issubset(body)
