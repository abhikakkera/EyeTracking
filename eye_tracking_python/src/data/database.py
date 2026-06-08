"""
SQLite database for local session storage.

Schema:
    sessions       — session metadata
    frame_records  — per-frame tracking data
    blink_events   — blink event log
    saccade_events — saccade event log
    fixation_events — fixation event log

All writes use parameterised queries (no string interpolation) to prevent
SQL injection.  The database file is created automatically on first use.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from src.data.schema import FrameQuality
from src.data.session_recorder import SessionData

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    subject_id TEXT,
    timestamp_start REAL,
    timestamp_end REAL,
    camera_type TEXT,
    camera_resolution TEXT,
    fps REAL,
    calibration_used INTEGER,
    test_type TEXT,
    software_version TEXT,
    total_frames INTEGER,
    good_frames INTEGER,
    blink_count INTEGER,
    saccade_count INTEGER,
    fixation_count INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS frame_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    frame_number INTEGER,
    timestamp_sec REAL,
    face_detected INTEGER,
    left_pupil_detected INTEGER,
    right_pupil_detected INTEGER,
    left_pupil_x REAL,
    left_pupil_y REAL,
    right_pupil_x REAL,
    right_pupil_y REAL,
    left_pupil_diameter_px REAL,
    right_pupil_diameter_px REAL,
    left_norm_x REAL,
    left_norm_y REAL,
    right_norm_x REAL,
    right_norm_y REAL,
    gaze_x REAL,
    gaze_y REAL,
    smooth_gaze_x REAL,
    smooth_gaze_y REAL,
    blink_detected INTEGER,
    left_ear REAL,
    right_ear REAL,
    gaze_velocity_px_per_sec REAL,
    gaze_acceleration REAL,
    confidence_score REAL,
    frame_quality TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS blink_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_timestamp_sec REAL,
    end_timestamp_sec REAL,
    duration_ms REAL,
    affected_eye TEXT,
    confidence REAL
);

CREATE TABLE IF NOT EXISTS saccade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_timestamp_sec REAL,
    end_timestamp_sec REAL,
    duration_ms REAL,
    amplitude_px REAL,
    peak_velocity_px_per_sec REAL,
    direction_deg REAL,
    start_x REAL,
    start_y REAL,
    end_x REAL,
    end_y REAL
);

CREATE TABLE IF NOT EXISTS fixation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_timestamp_sec REAL,
    end_timestamp_sec REAL,
    duration_ms REAL,
    center_x REAL,
    center_y REAL,
    dispersion_px REAL
);
"""


class EyeTrackingDatabase:
    """
    Thread-unsafe local SQLite store.  For research use only; not suitable
    for concurrent multi-process access without a locking wrapper.

    Usage:
        db = EyeTrackingDatabase("sessions/eye_tracking.db")
        db.open()
        db.save_session(session_data)
        db.close()
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        logger.info("Database opened: %s", self._path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def save_session(self, session: SessionData) -> None:
        """Write the entire session to the database in a single transaction."""
        if self._conn is None:
            raise RuntimeError("Database is not open. Call open() first.")

        meta = session.metadata
        with self._conn:
            # Session metadata
            self._conn.execute(
                """INSERT OR REPLACE INTO sessions VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    meta.session_id, meta.subject_id,
                    meta.timestamp_start, meta.timestamp_end,
                    meta.camera_type, json.dumps(list(meta.camera_resolution)),
                    meta.fps, int(meta.calibration_used),
                    meta.test_type.value, meta.software_version,
                    meta.total_frames, meta.good_frames,
                    meta.blink_count, meta.saccade_count,
                    meta.fixation_count, meta.notes,
                ),
            )

            # Frame records (batch insert)
            frame_rows = [
                (
                    r.session_id, r.frame_number, r.timestamp_sec,
                    int(r.face_detected),
                    int(r.left_pupil_detected), int(r.right_pupil_detected),
                    r.left_pupil_x, r.left_pupil_y,
                    r.right_pupil_x, r.right_pupil_y,
                    r.left_pupil_diameter_px, r.right_pupil_diameter_px,
                    r.left_norm_x, r.left_norm_y,
                    r.right_norm_x, r.right_norm_y,
                    r.gaze_x, r.gaze_y,
                    r.smooth_gaze_x, r.smooth_gaze_y,
                    int(r.blink_detected),
                    r.left_ear, r.right_ear,
                    r.gaze_velocity_px_per_sec, r.gaze_acceleration,
                    r.confidence_score, r.frame_quality.value,
                )
                for r in session.frames
            ]
            self._conn.executemany(
                """INSERT INTO frame_records
                (session_id,frame_number,timestamp_sec,face_detected,
                 left_pupil_detected,right_pupil_detected,
                 left_pupil_x,left_pupil_y,right_pupil_x,right_pupil_y,
                 left_pupil_diameter_px,right_pupil_diameter_px,
                 left_norm_x,left_norm_y,right_norm_x,right_norm_y,
                 gaze_x,gaze_y,smooth_gaze_x,smooth_gaze_y,
                 blink_detected,left_ear,right_ear,
                 gaze_velocity_px_per_sec,gaze_acceleration,
                 confidence_score,frame_quality)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                frame_rows,
            )

            # Events
            self._conn.executemany(
                "INSERT INTO blink_events VALUES (NULL,?,?,?,?,?,?)",
                [
                    (e.session_id, e.start_timestamp_sec, e.end_timestamp_sec,
                     e.duration_ms, e.affected_eye, e.confidence)
                    for e in session.blinks
                ],
            )
            self._conn.executemany(
                "INSERT INTO saccade_events VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (e.session_id, e.start_timestamp_sec, e.end_timestamp_sec,
                     e.duration_ms, e.amplitude_px, e.peak_velocity_px_per_sec,
                     e.direction_deg, e.start_x, e.start_y, e.end_x, e.end_y)
                    for e in session.saccades
                ],
            )
            self._conn.executemany(
                "INSERT INTO fixation_events VALUES (NULL,?,?,?,?,?,?,?)",
                [
                    (e.session_id, e.start_timestamp_sec, e.end_timestamp_sec,
                     e.duration_ms, e.center_x, e.center_y, e.dispersion_px)
                    for e in session.fixations
                ],
            )

        logger.info(
            "Session %s saved to database (%d frames, %d events)",
            meta.session_id[:8],
            len(session.frames),
            len(session.blinks) + len(session.saccades) + len(session.fixations),
        )

    def list_sessions(self) -> list:
        if self._conn is None:
            return []
        cur = self._conn.execute(
            "SELECT session_id, subject_id, timestamp_start, total_frames FROM sessions "
            "ORDER BY timestamp_start DESC"
        )
        return cur.fetchall()
