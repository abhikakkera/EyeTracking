"""
Tests for backend.db.database + backend.services.session_store using a
temporary SQLite database (PDEYE_DB_PATH override).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.paths import DISCLAIMER


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point the store at a throwaway DB + sessions dir."""
    monkeypatch.setenv("PDEYE_DB_PATH", str(tmp_path / "pdeye_test.db"))
    monkeypatch.setenv("PDEYE_SESSIONS_DIR", str(tmp_path / "sessions"))
    # Import lazily so the env vars are read fresh.
    from backend.services import session_store
    session_store.ensure_db()
    return session_store


def _summary(sid="s1", task="prosaccade"):
    return {
        "session_id": sid,
        "technical_task_name": task,
        "activity_name": "Look Toward the Dot",
        "date_time": "2026-06-08T12:00:00+00:00",
        "status": "completed",
        "subject_id": "anonymous",
        "duration_sec": 30.0,
        "fps": 30.0,
        "tracking_quality_label": "Good",
        "usable_data_percent": 82.4,
        "average_confidence": 0.84,
        "blink_count": 12,
        "rounds_completed": 20,
        "average_response_time_ms": 284.0,
        "task_metrics": {"fastest_response_ms": 210.0},
        "recommendations": ["The session had enough clear data for review."],
        "exports": {"trials": "/tmp/s1_trials.csv"},
        "disclaimer": DISCLAIMER,
    }


class TestSessionStore:
    def test_save_and_get(self, tmp_db):
        tmp_db.save_parsed(_summary("aaa11111"))
        got = tmp_db.get_summary("aaa11111")
        assert got is not None
        assert got["session_id"] == "aaa11111"
        assert got["activity_name"] == "Look Toward the Dot"
        assert got["usable_data_percent"] == 82.4
        assert got["task_metrics"]["fastest_response_ms"] == 210.0

    def test_list_summaries(self, tmp_db):
        tmp_db.save_parsed(_summary("aaa11111"))
        tmp_db.save_parsed(_summary("bbb22222", task="antisaccade"))
        rows = tmp_db.list_summaries()
        ids = {r["session_id"] for r in rows}
        assert {"aaa11111", "bbb22222"} <= ids
        # Lightweight rows expose the friendly name + quality
        row = next(r for r in rows if r["session_id"] == "aaa11111")
        assert row["activity_name"] == "Look Toward the Dot"
        assert row["tracking_quality_label"] == "Good"

    def test_record_pending_then_complete(self, tmp_db):
        tmp_db.record_pending("ccc33333", "gap_overlap", "anonymous", "running")
        rows = tmp_db.list_summaries()
        row = next(r for r in rows if r["session_id"] == "ccc33333")
        assert row["status"] == "running"

        # Now store a completed summary for the same id (upsert)
        s = _summary("ccc33333", task="gap_overlap")
        s["activity_name"] = "Quick Reaction Dot Task"
        tmp_db.save_parsed(s)
        got = tmp_db.get_summary("ccc33333")
        assert got["status"] == "completed"

    def test_get_unknown_returns_none(self, tmp_db):
        assert tmp_db.get_summary("does-not-exist") is None
