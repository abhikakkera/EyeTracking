-- PDEYE website session-summary store (local SQLite).
-- This is SEPARATE from the tracker's own eye_tracking.db: it holds only the
-- website-friendly summaries shown in the UI and the history table.

CREATE TABLE IF NOT EXISTS web_sessions (
    session_id              TEXT PRIMARY KEY,
    date_time               TEXT,      -- ISO 8601 start time
    task_type               TEXT,      -- prosaccade | antisaccade | gap_overlap | smooth_pursuit
    friendly_activity_name  TEXT,      -- "Look Toward the Dot", ...
    status                  TEXT,      -- preparing | running | completed | failed | cancelled
    subject_id              TEXT,
    tracking_quality_label  TEXT,      -- Excellent | Good | Okay | Needs better camera setup
    usable_data_percent     REAL,
    average_confidence      REAL,
    blink_count             INTEGER,
    rounds_completed        INTEGER,
    average_response_time_ms REAL,
    duration_sec            REAL,
    -- Full frontend-friendly summary JSON (so the results page can render from DB)
    summary_json            TEXT,
    -- Export file paths (absolute)
    summary_json_path       TEXT,
    frame_csv_path          TEXT,
    trial_csv_path          TEXT,
    events_json_path        TEXT,
    task_metadata_path      TEXT,
    html_report_path        TEXT,
    created_at              REAL       -- unix epoch when the row was written
);

CREATE INDEX IF NOT EXISTS idx_web_sessions_date ON web_sessions(date_time DESC);
