"""
SQLite access for the Ocula website store (sessions + user accounts).

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

# web_sessions columns we persist explicitly (named params; order irrelevant).
_COLUMNS = [
    "session_id", "user_id", "date_time", "task_type", "friendly_activity_name",
    "status", "subject_id", "tracking_quality_label", "usable_data_percent",
    "average_confidence", "blink_count", "rounds_completed",
    "average_response_time_ms", "duration_sec", "summary_json",
    "summary_json_path", "frame_csv_path", "trial_csv_path", "events_json_path",
    "task_metadata_path", "html_report_path", "created_at",
]

# Columns added after the first release — applied via ALTER on existing DBs.
_MIGRATIONS = [
    "ALTER TABLE web_sessions ADD COLUMN user_id INTEGER",
]

# Indexes are built *after* migrations so they can reference columns (e.g.
# user_id) that were ALTERed into a pre-existing database.
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_web_sessions_date ON web_sessions(date_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_web_sessions_user ON web_sessions(user_id)",
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables, apply column migrations, then build indexes.

    Order matters: a database created before ``user_id`` existed must have the
    column ALTERed in *before* any index references it — otherwise the index
    creation fails with ``no such column: user_id`` on upgrade.
    """
    schema = _SCHEMA_PATH.read_text()
    with _connect() as conn:
        conn.executescript(schema)  # tables only (idempotent)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        for stmt in _INDEXES:
            conn.execute(stmt)
    logger.info("Ocula database ready at %s", get_db_path())


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(email: str, name: str, password_hash: str) -> Dict[str, Any]:
    now = time.time()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (email.lower().strip(), name, password_hash, now, now),
        )
        uid = cur.lastrowid
    return get_user_by_id(uid)  # type: ignore[return-value]


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        )
        r = cur.fetchone()
    return dict(r) if r else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        r = cur.fetchone()
    return dict(r) if r else None


def update_user_name(user_id: int, name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET name = ?, updated_at = ? WHERE id = ?",
            (name, time.time(), user_id),
        )


def count_user_sessions(user_id: int) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM web_sessions WHERE user_id = ? AND status = 'completed'",
            (user_id,),
        )
        return int(cur.fetchone()["n"])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def upsert_session(row: Dict[str, Any]) -> None:
    """Insert or replace a web_sessions row. Missing keys → NULL."""
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


def get_session_owner(session_id: str) -> Optional[int]:
    row = get_session(session_id)
    if row is None:
        return None
    return row.get("user_id")


def list_sessions(limit: int = 100, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with _connect() as conn:
        if user_id is None:
            cur = conn.execute(
                "SELECT * FROM web_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM web_sessions WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]


def latest_completed_session_id(user_id: Optional[int] = None) -> Optional[str]:
    with _connect() as conn:
        if user_id is None:
            cur = conn.execute(
                "SELECT session_id FROM web_sessions "
                "WHERE status = 'completed' ORDER BY created_at DESC LIMIT 1"
            )
        else:
            cur = conn.execute(
                "SELECT session_id FROM web_sessions "
                "WHERE status = 'completed' AND user_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
        r = cur.fetchone()
    return r["session_id"] if r else None
