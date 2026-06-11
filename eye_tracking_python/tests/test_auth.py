"""
Tests for Ocula local authentication and per-user session isolation.
Auto-skips if FastAPI is not installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PDEYE_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("PDEYE_SESSIONS_DIR", str(tmp_path / "sessions"))
    from backend import app as appmod
    with TestClient(appmod.app) as c:
        yield c


def _signup(client, email="a@example.com", name="Alice", password="password123"):
    return client.post("/api/auth/signup",
                       json={"name": name, "email": email, "password": password})


# ---------------------------------------------------------------------------
# Signup / hashing
# ---------------------------------------------------------------------------

def test_signup_creates_user(client):
    r = _signup(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "a@example.com"
    assert body["user"]["name"] == "Alice"
    assert "password" not in json.dumps(body)  # never echoed back


def test_password_is_hashed_not_plaintext(client):
    _signup(client, email="hash@example.com", password="supersecret1")
    from backend.db import database
    row = database.get_user_by_email("hash@example.com")
    assert row is not None
    assert row["password_hash"] != "supersecret1"
    assert row["password_hash"].startswith("$2")  # bcrypt prefix


def test_duplicate_email_fails(client):
    assert _signup(client, email="dup@example.com").status_code == 200
    r = _signup(client, email="dup@example.com")
    assert r.status_code == 409


def test_short_password_rejected(client):
    r = _signup(client, email="short@example.com", password="short")
    assert r.status_code == 400


def test_invalid_email_rejected(client):
    r = _signup(client, email="not-an-email", password="password123")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_works(client):
    _signup(client, email="login@example.com", password="password123")
    r = client.post("/api/auth/login",
                    json={"email": "login@example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token"]


def test_wrong_password_fails(client):
    _signup(client, email="wrong@example.com", password="password123")
    r = client.post("/api/auth/login",
                    json={"email": "wrong@example.com", "password": "WRONGpassword"})
    assert r.status_code == 401


def test_me_returns_current_user(client):
    token = _signup(client, email="me@example.com").json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me@example.com"


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_protected_routes_require_auth(client):
    # No token → 401 on user-scoped endpoints.
    assert client.get("/api/sessions").status_code == 401
    assert client.get("/api/results/latest").status_code == 401
    assert client.post("/api/web-sessions/start",
                       json={"task_type": "prosaccade", "screen_width": 1280,
                             "screen_height": 720}).status_code == 401


# ---------------------------------------------------------------------------
# Per-user isolation
# ---------------------------------------------------------------------------

def _seed_session_for(client, token, sid):
    """Create a completed session owned by the token's user, via the store."""
    from backend.services import session_store
    from backend.paths import DISCLAIMER
    # Decode user id from the token
    from backend.services import auth_service
    uid = auth_service.user_id_from_token(token)
    session_store.record_pending(sid, "prosaccade", "p", "running", user_id=uid)
    session_store.save_parsed({
        "session_id": sid, "technical_task_name": "prosaccade",
        "activity_name": "Look Toward the Dot", "status": "completed",
        "tracking_quality_label": "Good", "usable_data_percent": 80.0,
        "rounds_completed": 12, "task_metrics": {}, "recommendations": [],
        "exports": {}, "disclaimer": DISCLAIMER,
    }, user_id=uid)


def test_user_cannot_access_another_users_session(client):
    a = _signup(client, email="ua@example.com").json()["token"]
    b = _signup(client, email="ub@example.com").json()["token"]
    _seed_session_for(client, a, "sessA001")

    # Owner can read it
    ra = client.get("/api/results/sessA001",
                    headers={"Authorization": f"Bearer {a}"})
    assert ra.status_code == 200

    # Other user gets 404 (not 403 — don't reveal existence)
    rb = client.get("/api/results/sessA001",
                    headers={"Authorization": f"Bearer {b}"})
    assert rb.status_code == 404


def test_dashboard_lists_only_own_sessions(client):
    a = _signup(client, email="la@example.com").json()["token"]
    b = _signup(client, email="lb@example.com").json()["token"]
    _seed_session_for(client, a, "ownA0001")
    _seed_session_for(client, b, "ownB0001")

    rows_a = client.get("/api/sessions",
                        headers={"Authorization": f"Bearer {a}"}).json()
    ids_a = {r["session_id"] for r in rows_a}
    assert "ownA0001" in ids_a
    assert "ownB0001" not in ids_a
