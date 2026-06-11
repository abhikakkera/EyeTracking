-- Ocula website store (local SQLite).
-- Separate from the tracker's eye_tracking.db: holds website session summaries,
-- the history table, and local user accounts.

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE NOT NULL,
    name            TEXT,
    password_hash   TEXT NOT NULL,
    created_at      REAL,
    updated_at      REAL
);

CREATE TABLE IF NOT EXISTS web_sessions (
    session_id              TEXT PRIMARY KEY,
    user_id                 INTEGER,   -- owner (NULL = legacy/anonymous)
    date_time               TEXT,      -- ISO 8601 start time
    task_type               TEXT,      -- prosaccade | antisaccade | gap_overlap | smooth_pursuit
    friendly_activity_name  TEXT,      -- "Look Toward the Dot", ...
    status                  TEXT,      -- preparing | running | completed | failed | cancelled
    subject_id              TEXT,
    tracking_quality_label  TEXT,
    usable_data_percent     REAL,
    average_confidence      REAL,
    blink_count             INTEGER,
    rounds_completed        INTEGER,
    average_response_time_ms REAL,
    duration_sec            REAL,
    summary_json            TEXT,      -- full frontend summary JSON
    summary_json_path       TEXT,
    frame_csv_path          TEXT,
    trial_csv_path          TEXT,
    events_json_path        TEXT,
    task_metadata_path      TEXT,
    html_report_path        TEXT,
    created_at              REAL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Indexes live in database.init_db() (the _INDEXES list), created *after*
-- column migrations run, so they can safely reference user_id on databases
-- that predate the accounts feature.
