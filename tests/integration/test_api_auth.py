from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import create_app
from tests.conftest import TEST_PASSWORD


def test_login_success_and_me():
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/login", json={"username": "enduser1", "password": TEST_PASSWORD})
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["user"]["role"] == "enduser"

        r2 = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["username"] == "enduser1"


def test_login_bad_password():
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/login", json={"username": "enduser1", "password": "wrong"})
        assert r.status_code == 401


def test_me_requires_bearer():
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/me")
        assert r.status_code == 401


def test_health():
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
