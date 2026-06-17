import io

from tests.conftest import auth


def _photo():
    return (io.BytesIO(b"fake-image-bytes"), "person.jpg")


def test_cases_listing_is_public(client):
    res = client.get("/api/cases/")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_create_case_requires_auth(client):
    res = client.post("/api/cases/", data={"name": "Nobody", "photos": _photo()},
                      content_type="multipart/form-data")
    assert res.status_code == 401


def test_create_case_validates_national_id(client, user_token, fake_face):
    res = client.post(
        "/api/cases/",
        data={"name": "Bad NIC", "national_id": "123", "photos": _photo()},
        content_type="multipart/form-data",
        headers=auth(user_token),
    )
    assert res.status_code == 400


def test_create_case_rejects_bad_extension(client, user_token, fake_face):
    res = client.post(
        "/api/cases/",
        data={"name": "Exe Upload", "photos": (io.BytesIO(b"x"), "malware.exe")},
        content_type="multipart/form-data",
        headers=auth(user_token),
    )
    assert res.status_code == 400


def test_create_case_success_and_fetch(client, user_token, fake_face):
    res = client.post(
        "/api/cases/",
        data={"name": "Ahmed Sarim", "national_id": "12345-1234567-1",
              "last_location": "Karachi", "photos": _photo()},
        content_type="multipart/form-data",
        headers=auth(user_token),
    )
    assert res.status_code == 201, res.get_data(as_text=True)
    case_id = res.get_json()["id"]

    got = client.get("/api/cases/%d" % case_id)
    assert got.status_code == 200
    assert got.get_json()["name"] == "Ahmed Sarim"


def test_status_update_is_admin_only(client, user_token, admin_token, fake_face):
    res = client.post(
        "/api/cases/",
        data={"name": "Status Case", "photos": _photo()},
        content_type="multipart/form-data",
        headers=auth(user_token),
    )
    case_id = res.get_json()["id"]

    # normal user forbidden
    r = client.put("/api/cases/%d/status" % case_id, json={"status": "solved"},
                   headers=auth(user_token))
    assert r.status_code == 403

    # admin allowed
    r = client.put("/api/cases/%d/status" % case_id, json={"status": "solved"},
                   headers=auth(admin_token))
    assert r.status_code == 200
    assert r.get_json()["status"] == "solved"
