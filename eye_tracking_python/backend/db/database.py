"""
SQLite access for the PDEYE website session store.

Local-only, no cloud.  Paths resolved via backend.paths (env-overridable for
tests).  All writes are parameterised.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.paths import get_db_path

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Columns we persist explicitly (order does not matter — we use named params).
_COLUMNS = [
    "session_id", "date_time", "task_type", "friendly_activity_name", "status",
    "subject_id", "tracking_quality_label", "usable_data_percent",
    "average_confidence", "blink_count", "rounds_completed",
    "average_response_time_ms", "duration_sec", "summary_json",
    "summary_json_path", "frame_csv_path", "trial_csv_path", "events_json_path",
    "task_metadata_path", "html_report_path", "created_at",
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the schema if it does not exist."""
    schema = _SCHEMA_PATH.read_text()
    with _connect() as conn:
        conn.executescript(schema)
    logger.info("PDEYE database ready at %s", get_db_path())


def upsert_session(row: Dict[str, Any]) -> None:
    """
    Insert or replace a web_sessions row.  Missing keys are stored as NULL.
    Always refreshes created_at.
    """
    data = {c: row.get(c) for c in _COLUMNS}
    if data.get("created_at") is None:
        data["created_at"] = time.time()

    placeholders = ", ".join(f":{c}" for c in _COLUMNS)
    columns = ", ".join(_COLUMNS)
    with _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO web_sessions ({columns}) VALUES ({placeholders})",
            data,
        )


def update_status(session_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE web_sessions SET status = ? WHERE session_id = ?",
            (status, session_id),
        )


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM web_sessions WHERE session_id = ?", (session_id,)
        )
        r = cur.fetchone()
    return dict(r) if r else None


def list_sessions(limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM web_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def latest_completed_session_id() -> Optional[str]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT session_id FROM web_sessions "
            "WHERE status = 'completed' ORDER BY created_at DESC LIMIT 1"
        )
        r = cur.fetchone()
    return r["session_id"] if r else None
