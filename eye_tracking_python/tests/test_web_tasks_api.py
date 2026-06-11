"""
Tests for the in-browser web task API (/api/web-sessions/*).

Uses real (synthetic) JPEG frames through the real tracker — no camera, no GUI.
Auto-skips if FastAPI is not installed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
import cv2  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _jpeg(width=640, height=480) -> bytes:
    img = np.full((height, width, 3), 90, dtype=np.uint8)
    cv2.circle(img, (width // 2, height // 2), 60, (200, 200, 200), -1)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PDEYE_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("PDEYE_SESSIONS_DIR", str(tmp_path / "sessions"))
    from backend import app as appmod
    with TestClient(appmod.app) as c:
        # Web sessions require a logged-in user — sign up and attach the token.
        r = c.post("/api/auth/signup", json={
            "name": "Test User", "email": "web@example.com", "password": "password123",
        })
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _start(client, task="prosaccade"):
    r = client.post("/api/web-sessions/start", json={
        "task_type": task, "participant_id": "anon",
        "screen_width": 1280, "screen_height": 720, "task_config": {"num_trials": 1},
    })
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _frame(client, sid, ts, gaze_phase="target", trial_id="t1", target_x=0.85):
    files = {"file": ("f.jpg", _jpeg(), "image/jpeg")}
    meta = {
        "browser_timestamp_ms": ts,
        "task_start_timestamp_ms": 0.0,
        "trial_id": trial_id,
        "trial_number": 1,
        "task_phase": gaze_phase,
        "recording_phase": "task",
        "target_visible": gaze_phase == "target",
        "target_x": target_x,
        "target_y": 0.5,
        "target_direction": "right",
        "condition": "none",
        "fixation_visible": gaze_phase == "fixation",
    }
    return client.post(f"/api/web-sessions/{sid}/frame",
                       files=files, data={"meta": json.dumps(meta)})


# ---------------------------------------------------------------------------

def test_web_config(client):
    r = client.get("/api/web-config")
    assert r.status_code == 200
    body = r.json()
    assert body["upload_fps"] >= 1
    assert "jpeg_quality" in body


def test_start_invalid_task(client):
    r = client.post("/api/web-sessions/start", json={"task_type": "bogus"})
    assert r.status_code == 400


def test_start_returns_session(client):
    sid = _start(client)
    assert isinstance(sid, str) and len(sid) == 8


def test_frame_endpoint_accepts_image(client):
    sid = _start(client)
    r = _frame(client, sid, 100.0)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tracking_status"] in ("good", "questionable", "bad")
    assert body["distance_status"] in ("good", "too_close", "too_far", "unknown")
    assert "guidance_message" in body
    assert body["frame_number"] == 0


def test_event_endpoint(client):
    sid = _start(client)
    r = client.post(f"/api/web-sessions/{sid}/event", json={
        "type": "trial_started", "timestamp_ms": 1000.0,
        "trial_id": "t1", "trial_number": 1, "direction": "right",
    })
    assert r.status_code == 200
    st = client.get(f"/api/web-sessions/{sid}/status").json()
    assert st["events_received"] == 1


def test_status_tracks_frames(client):
    sid = _start(client)
    _frame(client, sid, 100.0)
    _frame(client, sid, 200.0)
    st = client.get(f"/api/web-sessions/{sid}/status").json()
    assert st["frames_received"] == 2
    assert st["status"] == "running"


def test_full_session_complete_and_results(client):
    sid = _start(client)
    # Events for one prosaccade trial
    for ev in [
        {"type": "task_started", "timestamp_ms": 0.0, "task_start_timestamp_ms": 0.0},
        {"type": "trial_started", "timestamp_ms": 1000.0, "trial_id": "t1",
         "trial_number": 1, "direction": "right", "condition": "none"},
        {"type": "fixation_shown", "timestamp_ms": 1000.0, "trial_id": "t1"},
        {"type": "target_shown", "timestamp_ms": 2000.0, "trial_id": "t1",
         "target_x": 0.85, "target_y": 0.5},
        {"type": "trial_ended", "timestamp_ms": 2800.0, "trial_id": "t1"},
    ]:
        assert client.post(f"/api/web-sessions/{sid}/event", json=ev).status_code == 200

    # A handful of frames spanning fixation + target
    for ts in (1000.0, 1200.0, 1500.0, 2050.0, 2200.0, 2400.0):
        assert _frame(client, sid, ts).status_code == 200

    # Complete → summary
    r = client.post(f"/api/web-sessions/{sid}/complete")
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["activity_name"] == "Look Toward the Dot"
    assert summary["technical_task_name"] == "prosaccade"
    assert summary["rounds_completed"] == 1
    assert "disclaimer" in summary

    # New trial-quality diagnostics flow through end-to-end.
    diag = summary["diagnostics"]
    assert "no_face" in diag and "by_phase" in diag["no_face"]
    assert "well_tracked_trials" in diag
    assert "rounds_with_response" in diag
    assert isinstance(diag["trials_quality"], list) and len(diag["trials_quality"]) == 1
    tq = diag["trials_quality"][0]
    # Each round now carries response-window detail, a quality verdict + a reason.
    for key in ("usable_response_window_percent", "trial_quality",
                "no_face_near_target_onset", "longest_no_face_streak_ms"):
        assert key in tq
    # main_unclear_reason is now trial-level (never a raw frame-counter artifact).
    assert diag.get("main_unclear_reason") in (
        None, "no_tracking_data", "no_face_major", "insufficient_tracking",
        "insufficient_response_window_data", "no_face_at_target_onset",
        "no_face_brief_dropout", "blink_during_response_window",
    )

    # Stored + retrievable via the shared results route
    r2 = client.get(f"/api/results/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid

    # Files written to disk
    sdir = Path(os.environ["PDEYE_SESSIONS_DIR"])
    assert (sdir / f"{sid}_task_metadata.json").exists()
    assert (sdir / f"{sid}_trials.csv").exists()
    assert (sdir / f"{sid}_summary_report.json").exists()


def test_complete_without_frames_400(client):
    sid = _start(client)
    r = client.post(f"/api/web-sessions/{sid}/complete")
    assert r.status_code == 400
