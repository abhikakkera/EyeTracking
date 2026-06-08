"""
Tracker launcher — owns the lifecycle of the existing Python tracker subprocess.

Flow:
    start_run()  -> assigns a session_id, spawns `python main.py task <type>
                    --session-id <id> --out <sessions_dir>`, records a pending
                    row in the web store.
    get_status() -> polls the process; when it exits cleanly AND result files
                    exist, parses + stores the summary and reports 'completed'.
    stop_run()   -> terminates the process and marks the session 'cancelled'.

Only ONE run may be active at a time (the webcam is an exclusive resource).

The actual spawn is isolated in `_spawn()` so tests can monkeypatch it and never
open a real camera window.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from backend.paths import get_main_py, get_project_root, get_sessions_dir
from backend.services import result_parser, session_store

logger = logging.getLogger(__name__)

VALID_TASKS = {"prosaccade", "antisaccade", "gap_overlap", "smooth_pursuit"}

# Terminal states
_TERMINAL = {"completed", "failed", "cancelled"}


@dataclass
class RunHandle:
    session_id: str
    task_type: str
    subject_id: str
    status: str = "preparing"
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    proc: object = None           # subprocess.Popen (or a fake in tests)
    log_path: Optional[str] = None
    _log_fh: object = None


# In-memory registry of runs this server process has launched.
_RUNS: Dict[str, RunHandle] = {}


# ---------------------------------------------------------------------------
# Command construction (pure — easy to unit test)
# ---------------------------------------------------------------------------

def build_command(
    task_type: str,
    session_id: str,
    subject_id: str = "anonymous",
    trials: Optional[int] = None,
    pattern: Optional[str] = None,
    cycles: Optional[int] = None,
    sessions_dir: Optional[Path] = None,
) -> List[str]:
    if task_type not in VALID_TASKS:
        raise ValueError(f"Invalid task_type: {task_type}")

    out_dir = str(sessions_dir or get_sessions_dir())
    cmd = [
        sys.executable, str(get_main_py()),
        "task", task_type,
        "--subject", subject_id,
        "--session-id", session_id,
        "--out", out_dir,
    ]
    if trials:
        cmd += ["--trials", str(trials)]
    if task_type == "smooth_pursuit":
        if pattern:
            cmd += ["--pattern", pattern]
        if cycles:
            cmd += ["--cycles", str(cycles)]
    return cmd


# ---------------------------------------------------------------------------
# Active-run guard
# ---------------------------------------------------------------------------

def active_run() -> Optional[str]:
    """Return the session_id of a currently active run, if any."""
    for sid, h in _RUNS.items():
        if h.status in ("preparing", "running"):
            # Refresh status in case the process already exited
            _refresh(h)
            if h.status in ("preparing", "running"):
                return sid
    return None


# ---------------------------------------------------------------------------
# Spawn (isolated for tests)
# ---------------------------------------------------------------------------

def _spawn(cmd: List[str], log_path: Path):
    """Launch the tracker subprocess, redirecting output to a log file."""
    fh = open(log_path, "w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(get_project_root()),
        stdout=fh,
        stderr=subprocess.STDOUT,
    )
    return proc, fh


# ---------------------------------------------------------------------------
# Public lifecycle
# ---------------------------------------------------------------------------

def start_run(
    task_type: str,
    subject_id: str = "anonymous",
    trials: Optional[int] = None,
    pattern: Optional[str] = None,
    cycles: Optional[int] = None,
) -> RunHandle:
    """Launch a new tracker run. Raises RuntimeError if one is already active."""
    if task_type not in VALID_TASKS:
        raise ValueError(f"Invalid task_type: {task_type}")

    busy = active_run()
    if busy is not None:
        raise RuntimeError(f"A session is already running ({busy}). Stop it first.")

    session_id = uuid.uuid4().hex[:8]
    sessions_dir = get_sessions_dir()
    log_path = sessions_dir / f"{session_id}_tracker.log"
    cmd = build_command(task_type, session_id, subject_id, trials, pattern, cycles, sessions_dir)

    handle = RunHandle(
        session_id=session_id,
        task_type=task_type,
        subject_id=subject_id,
        status="preparing",
        log_path=str(log_path),
    )
    _RUNS[session_id] = handle

    session_store.record_pending(session_id, task_type, subject_id, status="running")

    try:
        proc, fh = _spawn(cmd, log_path)
        handle.proc = proc
        handle._log_fh = fh
        handle.status = "running"
        logger.info("Launched tracker: %s (session %s)", " ".join(cmd), session_id)
    except Exception as exc:  # noqa: BLE001
        handle.status = "failed"
        handle.error = f"Failed to launch tracker: {exc}"
        session_store.set_status(session_id, "failed")
        logger.exception("Launch failed for %s", session_id)

    return handle


def get_status(session_id: str) -> Dict[str, object]:
    """Return the current status dict for a session (refreshing live processes)."""
    handle = _RUNS.get(session_id)
    if handle is None:
        # Unknown to this server instance — infer from disk/store.
        return _status_from_disk(session_id)

    _refresh(handle)
    return _status_dict(handle)


def stop_run(session_id: str) -> Dict[str, object]:
    """Terminate a running tracker and mark the session cancelled."""
    handle = _RUNS.get(session_id)
    if handle is None:
        return {"session_id": session_id, "status": "not_found"}

    proc = handle.proc
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error terminating %s: %s", session_id, exc)

    handle.status = "cancelled"
    _close_log(handle)
    session_store.set_status(session_id, "cancelled")
    return _status_dict(handle)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _refresh(handle: RunHandle) -> None:
    """Poll a running process and finalize on exit."""
    if handle.status in _TERMINAL:
        return
    proc = handle.proc
    if proc is None:
        return

    code = proc.poll()
    if code is None:
        handle.status = "running"
        return

    # Process has exited — decide completed vs failed.
    _close_log(handle)
    files = result_parser.session_files(handle.session_id)
    if files["task_metadata"].exists():
        try:
            summary = result_parser.parse_session(handle.session_id)
            session_store.save_parsed(summary)
            handle.status = "completed"
            return
        except Exception as exc:  # noqa: BLE001
            handle.status = "failed"
            handle.error = f"Result parsing failed: {exc}"
            session_store.set_status(handle.session_id, "failed")
            return

    # No result files: treat as failed and surface a log tail.
    handle.status = "failed"
    handle.error = _log_tail(handle) or f"Tracker exited with code {code} and no results."
    session_store.set_status(handle.session_id, "failed")


def _status_from_disk(session_id: str) -> Dict[str, object]:
    """For sessions not in this server's registry, infer status from files/store."""
    files = result_parser.session_files(session_id)
    if files["task_metadata"].exists():
        try:
            summary = session_store.get_summary(session_id)
            if summary is None:
                summary = result_parser.parse_session(session_id)
                session_store.save_parsed(summary)
        except Exception:  # noqa: BLE001
            pass
        return {"session_id": session_id, "status": "completed", "error": None}
    # Otherwise check the store
    stored = session_store.list_summaries(limit=500)
    for r in stored:
        if r["session_id"] == session_id:
            return {"session_id": session_id, "status": r["status"], "error": None}
    return {"session_id": session_id, "status": "not_found", "error": None}


def _status_dict(handle: RunHandle) -> Dict[str, object]:
    return {
        "session_id": handle.session_id,
        "task_type": handle.task_type,
        "status": handle.status,
        "error": handle.error,
    }


def _close_log(handle: RunHandle) -> None:
    if handle._log_fh is not None:
        try:
            handle._log_fh.close()
        except Exception:  # noqa: BLE001
            pass
        handle._log_fh = None


def _log_tail(handle: RunHandle, n: int = 1200) -> Optional[str]:
    if not handle.log_path:
        return None
    try:
        text = Path(handle.log_path).read_text()
        return text[-n:].strip() or None
    except Exception:  # noqa: BLE001
        return None
