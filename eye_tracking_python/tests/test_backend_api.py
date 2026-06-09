"""
Tests for the PDEYE FastAPI backend.

The tracker subprocess is mocked (tracker_launcher._spawn is monkeypatched) so
no camera window is ever opened. Skipped automatically if FastAPI is not
installed (i.e. before `pip install -r backend/requirements.txt`).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from backend.paths import DISCLAIMER  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeProc:
    """Minimal stand-in for subprocess.Popen."""
    def __init__(self, exit_code):
        self._code = exit_code
        self.terminated = False

    def poll(self):
        return self._code

    def terminate(self):
        self.terminated = True
        self._code = -15

    def wait(self, timeout=None):
        return self._code

    def kill(self):
        self._code = -9


def _write_min_session(sessions: Path, sid: str, task: str = "prosaccade") -> None:
    sessions.mkdir(parents=True, exist_ok=True)
    analysis = {
        "task_type": task,
        "total_trials": 10,
        "response_count": 8,
        "response_rate": 0.8,
        "correct_count": 7,
        "direction_accuracy": 0.875,
        "mean_latency_ms": 265.0,
        "sd_latency_ms": 30.0,
        "min_latency_ms": 210.0,
        "max_latency_ms": 320.0,
        "mean_peak_velocity_px_per_sec": 450.0,
        "left_accuracy": 0.8,
        "right_accuracy": 0.95,
        "disclaimer": DISCLAIMER,
    }
    (sessions / f"{sid}_task_metadata.json").write_text(json.dumps({
        "session_id": sid, "task_id": "t", "task_type": task, "subject_id": "anonymous",
        "software_version": "0.3.0", "timestamp_start": 1700000000.0,
        "timestamp_end": 1700000030.0, "duration_sec": 30.0,
        "num_completed_trials": 10, "task_config": {}, "analysis": analysis,
        "disclaimer": DISCLAIMER,
    }))
    (sessions / f"{sid}_metadata.json").write_text(json.dumps({
        "session_id": sid,
        "summary": {"total_frames": 100, "good_frames": 84, "good_frame_ratio": 0.84,
                    "blink_count": 7},
    }))
    # Real frames.csv so the strict usable-data calc has data:
    # 84 fully-usable frames, 16 face-only (no pupil, low confidence).
    header = ("frame_number,face_detected,left_eye_detected,right_eye_detected,"
              "left_pupil_detected,right_pupil_detected,blink_detected,"
              "frame_quality,confidence_score")
    rows = [header]
    for i in range(100):
        if i < 84:
            rows.append(f"{i},1,1,1,1,1,0,good,0.9")
        else:
            rows.append(f"{i},1,1,1,0,0,0,questionable,0.2")
    (sessions / f"{sid}_frames.csv").write_text("\n".join(rows) + "\n")
    # 10 trials, 8 with a detected response.
    trial_rows = ["trial_number,response_detected"]
    for i in range(10):
        trial_rows.append(f"{i + 1},{1 if i < 8 else 0}")
    (sessions / f"{sid}_trials.csv").write_text("\n".join(trial_rows) + "\n")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PDEYE_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("PDEYE_SESSIONS_DIR", str(tmp_path / "sessions"))
    from backend.services import tracker_launcher
    tracker_launcher._RUNS.clear()
    return tmp_path


@pytest.fixture()
def client(env):
    from backend import app as appmod
    with TestClient(appmod.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "research prototype" in body["disclaimer"].lower()


def test_tasks_list(client):
    r = client.get("/api/tasks")
    assert r.status_code == 200
    types = {t["task_type"] for t in r.json()["tasks"]}
    assert types == {"prosaccade", "antisaccade", "gap_overlap", "smooth_pursuit"}


def test_build_command():
    from backend.services import tracker_launcher
    cmd = tracker_launcher.build_command(
        "prosaccade", "sid12345", "p1", trials=5, sessions_dir=Path("/tmp/x"),
    )
    joined = " ".join(cmd)
    assert "main.py" in joined
    assert "task" in cmd and "prosaccade" in cmd
    assert "--session-id" in cmd and "sid12345" in cmd
    assert "--out" in cmd
    assert "--trials" in cmd and "5" in cmd


def test_invalid_task_rejected(client):
    r = client.post("/api/tests/start", json={"task_type": "not_a_task"})
    assert r.status_code == 400


def test_start_completes_and_parses(client, env, monkeypatch):
    from backend.services import tracker_launcher

    def fake_spawn(cmd, log_path):
        sid = cmd[cmd.index("--session-id") + 1]
        _write_min_session(env / "sessions", sid, "prosaccade")
        Path(log_path).write_text("done")
        return FakeProc(0), open(log_path, "a")

    monkeypatch.setattr(tracker_launcher, "_spawn", fake_spawn)

    r = client.post("/api/tests/start", json={"task_type": "prosaccade"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["task_type"] == "prosaccade"

    # Process already "exited" → first status poll finalizes to completed.
    r2 = client.get(f"/api/tests/status/{sid}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"

    # Result is parsed and friendly.
    r3 = client.get(f"/api/results/{sid}")
    assert r3.status_code == 200
    assert r3.json()["activity_name"] == "Look Toward the Dot"
    assert r3.json()["tracking_quality_label"] == "Good"  # 84%

    # Shows up in history.
    r4 = client.get("/api/sessions")
    assert any(row["session_id"] == sid for row in r4.json())


def test_only_one_run_at_a_time(client, monkeypatch):
    from backend.services import tracker_launcher

    def fake_spawn_running(cmd, log_path):
        Path(log_path).write_text("running")
        return FakeProc(None), open(log_path, "a")  # poll() -> None == still running

    monkeypatch.setattr(tracker_launcher, "_spawn", fake_spawn_running)

    r1 = client.post("/api/tests/start", json={"task_type": "prosaccade"})
    assert r1.status_code == 200
    sid = r1.json()["session_id"]

    # Second start while the first is "running" must be rejected.
    r2 = client.post("/api/tests/start", json={"task_type": "antisaccade"})
    assert r2.status_code == 409

    # Stop the first so we don't leak a fake process.
    client.post(f"/api/tests/stop/{sid}")


def test_latest_result_404_when_empty(client):
    r = client.get("/api/results/latest")
    assert r.status_code == 404
