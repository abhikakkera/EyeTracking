"""
Session store — bridges parsed summaries and the SQLite web_sessions table.

Keeps the database in sync with parsed results and exposes lightweight rows for
the history page.  Stores the full frontend summary as JSON so the results page
can render entirely from the database without re-parsing files.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from backend.db import database
from backend.services import result_parser

logger = logging.getLogger(__name__)


def ensure_db() -> None:
    database.init_db()


def record_pending(session_id: str, task_type: str, subject_id: str, status: str) -> None:
    """Insert a placeholder row when a test is started (status preparing/running)."""
    ensure_db()
    database.upsert_session({
        "session_id": session_id,
        "task_type": task_type,
        "friendly_activity_name": result_parser.friendly_name(task_type),
        "status": status,
        "subject_id": subject_id,
        "date_time": None,
        "created_at": time.time(),
    })


def set_status(session_id: str, status: str) -> None:
    ensure_db()
    existing = database.get_session(session_id)
    if existing:
        database.update_status(session_id, status)


def save_parsed(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a parsed summary (from result_parser.parse_session) into the DB.
    Returns the same summary.
    """
    ensure_db()
    exports = summary.get("exports", {}) or {}
    row = {
        "session_id": summary["session_id"],
        "date_time": summary.get("date_time"),
        "task_type": summary.get("technical_task_name"),
        "friendly_activity_name": summary.get("activity_name"),
        "status": summary.get("status", "completed"),
        "subject_id": summary.get("subject_id", "anonymous"),
        "tracking_quality_label": summary.get("tracking_quality_label"),
        "usable_data_percent": summary.get("usable_data_percent"),
        "average_confidence": summary.get("average_confidence"),
        "blink_count": summary.get("blink_count"),
        "rounds_completed": summary.get("rounds_completed"),
        "average_response_time_ms": summary.get("average_response_time_ms"),
        "duration_sec": summary.get("duration_sec"),
        "summary_json": json.dumps(summary),
        "summary_json_path": exports.get("task_metadata"),
        "frame_csv_path": exports.get("frames"),
        "trial_csv_path": exports.get("trials"),
        "events_json_path": exports.get("events"),
        "task_metadata_path": exports.get("task_metadata"),
        "html_report_path": summary.get("html_report_path"),
        "created_at": time.time(),
    }
    database.upsert_session(row)
    logger.info("Stored summary for session %s", summary["session_id"])
    return summary


def get_summary(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the full frontend summary for a session.

    The exported files are the source of truth, so we RE-PARSE from disk
    whenever they exist (this makes parser/quality fixes apply to sessions that
    were recorded before the fix). The stored JSON is only used as a fallback
    when the files are gone, and to preserve web-only event diagnostics that
    cannot be recomputed from files.
    """
    ensure_db()
    row = database.get_session(session_id)
    stored: Optional[Dict[str, Any]] = None
    if row and row.get("summary_json"):
        try:
            stored = json.loads(row["summary_json"])
        except Exception:  # noqa: BLE001
            stored = None

    try:
        fresh = result_parser.parse_session(session_id)
    except result_parser.SessionNotFound:
        return stored  # files removed — return whatever we cached, if anything

    # Preserve web-only diagnostics (event counts, per-trial quality) that the
    # file-based parser cannot recompute.
    if (stored and isinstance(stored.get("diagnostics"), dict)
            and isinstance(fresh.get("diagnostics"), dict)):
        for k in ("task_events_received", "target_onset_events_received",
                  "bad_trials", "trials_quality"):
            v = stored["diagnostics"].get(k)
            if v is not None and fresh["diagnostics"].get(k) in (None, 0):
                fresh["diagnostics"][k] = v
        if stored.get("mode"):
            fresh["mode"] = stored["mode"]

    return save_parsed(fresh)


def list_summaries(limit: int = 100) -> List[Dict[str, Any]]:
    """Lightweight rows for the history table."""
    ensure_db()
    rows = database.list_sessions(limit)
    out = []
    for r in rows:
        out.append({
            "session_id": r["session_id"],
            "date_time": r["date_time"],
            "task_type": r["task_type"],
            "activity_name": r["friendly_activity_name"],
            "status": r["status"],
            "tracking_quality_label": r["tracking_quality_label"],
            "usable_data_percent": r["usable_data_percent"],
            "rounds_completed": r["rounds_completed"],
            "average_response_time_ms": r["average_response_time_ms"],
        })
    return out


def get_exports(session_id: str) -> Dict[str, str]:
    """Return existing export files for a session as {kind: absolute_path}."""
    return result_parser.existing_exports(session_id)
