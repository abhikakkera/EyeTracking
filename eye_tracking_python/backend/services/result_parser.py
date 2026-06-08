"""
Result parser — converts tracker output files into website-friendly summaries.

Reads (per session id):
    <sid>_task_metadata.json   (required for a completed task session)
    <sid>_metadata.json        (eye-tracking summary: good_frame_ratio, blinks)
    <sid>_frames.csv           (fallback for usable% / confidence if needed)
    <sid>_trials.csv           (fallback round counts)

Produces a single dict matching the frontend `SessionSummary` type.

IMPORTANT: this module performs NO medical interpretation.  It reports task
performance metrics and tracking quality only.  All language is research-only.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.paths import DISCLAIMER, get_sessions_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Naming + labels
# ---------------------------------------------------------------------------

FRIENDLY_NAMES: Dict[str, str] = {
    "prosaccade":     "Look Toward the Dot",
    "antisaccade":    "Look Away from the Dot",
    "gap_overlap":    "Quick Reaction Dot Task",
    "smooth_pursuit": "Follow the Moving Dot",
}


def friendly_name(task_type: str) -> str:
    return FRIENDLY_NAMES.get(task_type, task_type.replace("_", " ").title())


def quality_label(usable_percent: Optional[float]) -> str:
    """Map usable-data percentage to a friendly tracking-quality label."""
    if usable_percent is None:
        return "Okay"
    if usable_percent >= 85:
        return "Excellent"
    if usable_percent >= 70:
        return "Good"
    if usable_percent >= 50:
        return "Okay"
    return "Needs better camera setup"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SessionNotFound(Exception):
    """Raised when a session's result files cannot be located."""


def session_files(session_id: str, sessions_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Return a dict of expected export paths for a session (whether or not they exist)."""
    d = Path(sessions_dir) if sessions_dir else get_sessions_dir()
    return {
        "task_metadata": d / f"{session_id}_task_metadata.json",
        "metadata":      d / f"{session_id}_metadata.json",
        "trials":        d / f"{session_id}_trials.csv",
        "frames":        d / f"{session_id}_frames.csv",
        "task_frames":   d / f"{session_id}_task_frames.csv",
        "events":        d / f"{session_id}_events.json",
        "saccades":      d / f"{session_id}_saccades.csv",
        "fixations":     d / f"{session_id}_fixations.csv",
        "blinks":        d / f"{session_id}_blinks.csv",
    }


def existing_exports(session_id: str, sessions_dir: Optional[Path] = None) -> Dict[str, str]:
    """Return only the export files that actually exist, as {kind: absolute_path}."""
    return {
        kind: str(p)
        for kind, p in session_files(session_id, sessions_dir).items()
        if p.exists()
    }


def find_latest_completed(sessions_dir: Optional[Path] = None) -> Optional[str]:
    """Find the newest session id that has a *_task_metadata.json on disk."""
    d = Path(sessions_dir) if sessions_dir else get_sessions_dir()
    candidates = sorted(
        d.glob("*_task_metadata.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0].name.replace("_task_metadata.json", "")


def parse_session(session_id: str, sessions_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Parse one completed task session into a frontend-friendly summary dict.

    Raises SessionNotFound if the task metadata file is missing.
    """
    files = session_files(session_id, sessions_dir)
    tm_path = files["task_metadata"]
    if not tm_path.exists():
        raise SessionNotFound(f"No task metadata for session {session_id}")

    tm = _read_json(tm_path) or {}
    md = _read_json(files["metadata"]) or {}

    task_type = tm.get("task_type", "unknown")
    analysis = tm.get("analysis", {}) or {}
    eye_summary = md.get("summary", {}) or {}

    # ---- usable data % + blink count (prefer eye metadata, fall back to CSV) ----
    good_ratio = eye_summary.get("good_frame_ratio")
    usable_percent = (
        round(good_ratio * 100, 1) if good_ratio is not None
        else _usable_percent_from_frames(files["frames"])
    )
    blink_count = eye_summary.get("blink_count")
    if blink_count is None:
        blink_count = 0

    average_confidence = _mean_confidence_from_frames(files["frames"])

    # ---- per-task metrics + headline numbers ----
    task_metrics, rounds_completed, avg_rt = _build_task_metrics(task_type, analysis)

    label = quality_label(usable_percent)

    summary: Dict[str, Any] = {
        "session_id": session_id,
        "technical_task_name": task_type,
        "activity_name": friendly_name(task_type),
        "date_time": _iso_from_epoch(tm.get("timestamp_start")),
        "status": "completed",
        "subject_id": tm.get("subject_id", "anonymous"),
        "duration_sec": tm.get("duration_sec"),
        "fps": md.get("fps"),
        "tracking_quality_label": label,
        "usable_data_percent": usable_percent,
        "average_confidence": average_confidence,
        "blink_count": int(blink_count),
        "rounds_completed": rounds_completed,
        "average_response_time_ms": avg_rt,
        "task_metrics": task_metrics,
        "recommendations": _recommendations(usable_percent, blink_count, label),
        "exports": existing_exports(session_id, sessions_dir),
        "disclaimer": DISCLAIMER,
    }
    return summary


# ---------------------------------------------------------------------------
# Per-task metric shaping
# ---------------------------------------------------------------------------

def _build_task_metrics(task_type: str, a: Dict[str, Any]):
    """Return (task_metrics dict, rounds_completed, average_response_time_ms)."""
    if task_type == "prosaccade":
        total = a.get("total_trials", 0)
        responded = a.get("response_count", 0)
        metrics = {
            "average_response_time_ms": a.get("mean_latency_ms"),
            "fastest_response_ms": a.get("min_latency_ms"),
            "successful_clear_rounds": a.get("correct_count", 0),
            "unclear_rounds": max(0, total - responded),
            "direction_accuracy_percent": _pct(a.get("direction_accuracy")),
            "left_accuracy_percent": _pct(a.get("left_accuracy")),
            "right_accuracy_percent": _pct(a.get("right_accuracy")),
            "response_rate_percent": _pct(a.get("response_rate")),
        }
        return metrics, total, a.get("mean_latency_ms")

    if task_type == "antisaccade":
        total = a.get("total_trials", 0)
        responded = a.get("response_count", 0)
        metrics = {
            "correct_direction_rounds": a.get("correct_count", 0),
            "average_response_time_ms": a.get("mean_correct_latency_ms"),
            "self_corrections": a.get("correction_count", 0),
            "error_rate_percent": _pct(a.get("error_rate")),
            "correction_rate_percent": _pct(a.get("correction_rate")),
            "unclear_rounds": max(0, total - responded),
        }
        return metrics, total, a.get("mean_correct_latency_ms")

    if task_type == "gap_overlap":
        total = a.get("total_trials", 0)
        metrics = {
            "average_response_time_gap_ms": a.get("mean_gap_latency_ms"),
            "average_response_time_overlap_ms": a.get("mean_overlap_latency_ms"),
            "gap_effect_ms": a.get("gap_effect_ms"),
            "gap_valid_rounds": int(round((a.get("gap_response_rate", 0) or 0) * a.get("gap_trials", 0))),
            "overlap_valid_rounds": int(round((a.get("overlap_response_rate", 0) or 0) * a.get("overlap_trials", 0))),
            "gap_trials": a.get("gap_trials", 0),
            "overlap_trials": a.get("overlap_trials", 0),
        }
        # Headline RT = mean of the two conditions that have data
        rts = [v for v in (a.get("mean_gap_latency_ms"), a.get("mean_overlap_latency_ms")) if v]
        avg = round(sum(rts) / len(rts), 1) if rts else None
        return metrics, total, avg

    if task_type == "smooth_pursuit":
        total = a.get("total_cycles", 0)
        metrics = {
            "mean_pursuit_gain": a.get("mean_pursuit_gain"),
            "mean_position_error_px": a.get("mean_position_error_px"),
            "time_on_target_percent": _pct(a.get("mean_time_on_target")),
            "total_catch_up_saccades": a.get("total_catch_up_saccades", 0),
        }
        return metrics, total, None

    return {}, a.get("total_trials", a.get("total_cycles", 0)), None


# ---------------------------------------------------------------------------
# Recommendations (research-only, friendly language)
# ---------------------------------------------------------------------------

def _recommendations(usable: Optional[float], blinks: int, label: str) -> List[str]:
    recs: List[str] = []
    if usable is None or usable < 50:
        recs.append("Tracking was limited this time. Try sitting a little closer to the camera.")
        recs.append("Better, even lighting on your face may improve tracking.")
    elif usable < 70:
        recs.append("Tracking was usable. Try keeping your head centered and still next time.")
    else:
        recs.append("The session had enough clear data for review.")

    if usable is not None and 50 <= usable < 85:
        recs.append("Sitting squarely in front of the camera can improve data quality.")

    if blinks and blinks > 40:
        recs.append("Frequent blinking was detected — that is normal, but resting your eyes beforehand can help.")

    return recs[:3]


# ---------------------------------------------------------------------------
# CSV fallbacks
# ---------------------------------------------------------------------------

def _usable_percent_from_frames(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    total = good = 0
    try:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                total += 1
                if (row.get("frame_quality") or "").strip().lower() == "good":
                    good += 1
    except Exception:  # noqa: BLE001
        return None
    return round(100.0 * good / total, 1) if total else None


def _mean_confidence_from_frames(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    vals: List[float] = []
    try:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("face_detected") or "0") in ("1", "True", "true"):
                    try:
                        vals.append(float(row.get("confidence_score") or 0.0))
                    except ValueError:
                        pass
    except Exception:  # noqa: BLE001
        return None
    return round(sum(vals) / len(vals), 3) if vals else None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        logger.warning("Could not parse JSON: %s", path)
        return None


def _iso_from_epoch(epoch: Optional[float]) -> Optional[str]:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


def _pct(ratio: Optional[float]) -> Optional[float]:
    if ratio is None:
        return None
    return round(float(ratio) * 100, 1)
