"""
Centralised path resolution for the Ocula backend.

All paths can be overridden via environment variables so tests can point at a
temporary directory:

    PDEYE_SESSIONS_DIR   directory where the tracker writes session files
                         (default: <project_root>/sessions)
    PDEYE_DB_PATH        SQLite database for website session summaries
                         (default: <sessions_dir>/pdeye.db)

The project root is the existing eye-tracking project (the directory that
contains main.py, config.py, and src/).  The backend lives inside it.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/paths.py  ->  backend/  ->  <project_root>
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The shared disclaimer text — must be identical everywhere it appears.
DISCLAIMER = (
    "This software is a research prototype for eye-tracking data collection. "
    "It does not diagnose, treat, predict, or screen for Parkinson's disease "
    "or any other medical condition. Clinical use would require validation, "
    "regulatory review, and healthcare professional oversight."
)


def get_project_root() -> Path:
    return PROJECT_ROOT


def get_sessions_dir() -> Path:
    """Directory where the tracker writes <session_id>_*.csv/json files."""
    env = os.environ.get("PDEYE_SESSIONS_DIR")
    p = Path(env) if env else PROJECT_ROOT / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path() -> Path:
    """SQLite database file for website session summaries."""
    env = os.environ.get("PDEYE_DB_PATH")
    if env:
        p = Path(env)
    else:
        p = get_sessions_dir() / "pdeye.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_main_py() -> Path:
    """Path to the tracker CLI entry point."""
    return PROJECT_ROOT / "main.py"
