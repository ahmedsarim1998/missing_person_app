"""
Shared pytest fixtures.

The face-recognition engine (TensorFlow) is NOT loaded during tests: FaceModel
is replaced with a lightweight fake so the API/auth/RBAC logic can be tested
fast and offline.
"""

import os
import sys
import tempfile

import numpy as np
import pytest

# Make the backend package importable (tests live in backend/tests).
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Configure a clean, isolated test environment BEFORE importing the app.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ["APP_ENV"] = "testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///" + _DB_PATH.replace("\\", "/")
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"
os.environ["LOGIN_MAX_ATTEMPTS"] = "1000"
os.environ["LOG_DIR"] = tempfile.mkdtemp()
os.environ["UPLOAD_FOLDER"] = tempfile.mkdtemp()

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402


class FakeFaceModel:
    """Stand-in for utils.face_recognition.FaceModel (no TensorFlow)."""

    def detect_faces(self, image):
        return [{"box": [0, 0, 10, 10]}]

    def extract_face(self, image, box, required_size=(160, 160)):
        return np.ones((160, 160, 3), dtype="uint8")

    def get_embedding(self, face_image):
        return np.ones(128, dtype="float32")

    def distance(self, a, b):
        return float(np.linalg.norm(a - b))


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    yield application
    with application.app_context():
        db.session.remove()
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def fake_face(monkeypatch):
    import routes.cases as cases_mod
    from utils.face_recognition import FaceModel

    fake = FakeFaceModel()
    monkeypatch.setattr(FaceModel, "get_instance", staticmethod(lambda: fake))
    # cv2.imread would return None for our dummy bytes; force a valid array.
    monkeypatch.setattr(cases_mod.cv2, "imread", lambda path: np.zeros((20, 20, 3), dtype="uint8"))
    return fake


@pytest.fixture()
def admin_token(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin-test-pass"})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["access_token"]


@pytest.fixture()
def user_token(client):
    client.post("/api/auth/signup", json={
        "username": "tester", "password": "password123",
        "email": "tester@example.com", "first_name": "Test", "last_name": "User",
    })
    res = client.post("/api/auth/login", json={"username": "tester", "password": "password123"})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["access_token"]


def auth(token):
    return {"Authorization": "Bearer " + token}
