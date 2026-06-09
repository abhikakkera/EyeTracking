"""
Result parser — converts tracker output files into website-friendly summaries.

v0.5 fixes (the "Excellent but 0 responses" contradiction):
  • usable_data_percent now means REAL usable eye-tracking frames
    (face AND eye AND pupil/gaze AND confidence>=thresh AND quality!=bad AND
    not a blink) divided by total frames — NOT just "frame quality good".
  • tracking_quality_label now considers usable%, confidence AND valid-trial
    ratio together, so a session with zero clear responses can never be
    "Excellent".
  • missing metrics are None (→ "N/A" in the UI), never 0.
  • per-task metric sets only include task-appropriate fields.
  • a `diagnostics` block exposes the underlying counts for debugging.

NO medical interpretation — task performance + tracking quality only.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.paths import DISCLAIMER, get_sessions_dir

logger = logging.getLogger(__name__)

# A frame counts as "usable eye-tracking data" only at/above this confidence.
USABLE_CONFIDENCE_THRESHOLD = 0.40


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


def quality_label(
    usable_percent: Optional[float],
    avg_confidence: Optional[float],
    valid_trials: int,
    total_trials: int,
) -> str:
    """
    Multi-factor tracking-quality label.

    Tracking quality is tied to BOTH real usable frames and whether the task
    actually produced valid trials — so an empty session cannot read "Excellent".
    """
    u = usable_percent if usable_percent is not None else 0.0
    c = avg_confidence if avg_confidence is not None else 0.0
    valid_ratio = (valid_trials / total_trials) if total_trials else 0.0

    # Hard floor: no valid trials, or too little usable data → needs setup.
    if total_trials == 0 or valid_trials == 0 or u < 60:
        return "Needs better camera setup"
    if u >= 90 and c >= 0.85 and valid_ratio >= 0.80:
        return "Excellent"
    if u >= 75 and c >= 0.70 and valid_ratio >= 0.60:
        return "Good"
    if u >= 60 and valid_trials > 0:
        return "Okay"
    return "Needs better camera setup"


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

class SessionNotFound(Exception):
    """Raised when a session's result files cannot be located."""


def session_files(session_id: str, sessions_dir: Optional[Path] = None) -> Dict[str, Path]:
    d = Path(sessions_dir) if sessions_dir else get_sessions_dir()
    return {
        "task_metadata":  d / f"{session_id}_task_metadata.json",
        "metadata":       d / f"{session_id}_metadata.json",
        "trials":         d / f"{session_id}_trials.csv",
        "frames":         d / f"{session_id}_frames.csv",
        "task_frames":    d / f"{session_id}_task_frames.csv",
        "events":         d / f"{session_id}_events.json",
        "saccades":       d / f"{session_id}_saccades.csv",
        "fixations":      d / f"{session_id}_fixations.csv",
        "blinks":         d / f"{session_id}_blinks.csv",
        "summary_report": d / f"{session_id}_summary_report.json",
        "task_config":    d / f"{session_id}_task_config.json",
    }


def existing_exports(session_id: str, sessions_dir: Optional[Path] = None) -> Dict[str, str]:
    return {
        kind: str(p)
        for kind, p in session_files(session_id, sessions_dir).items()
        if p.exists()
    }


def find_latest_completed(sessions_dir: Optional[Path] = None) -> Optional[str]:
    d = Path(sessions_dir) if sessions_dir else get_sessions_dir()
    candidates = sorted(
        d.glob("*_task_metadata.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].name.replace("_task_metadata.json", "") if candidates else None


# ---------------------------------------------------------------------------
# Main parse
# ---------------------------------------------------------------------------

def parse_session(
    session_id: str,
    sessions_dir: Optional[Path] = None,
    extra_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Parse one completed task session into a frontend-friendly summary dict.

    `extra_diagnostics` (web sessions) augments the file-derived diagnostics
    with event counts and richer per-frame reasons.
    """
    files = session_files(session_id, sessions_dir)
    if not files["task_metadata"].exists():
        raise SessionNotFound(f"No task metadata for session {session_id}")

    tm = _read_json(files["task_metadata"]) or {}
    md = _read_json(files["metadata"]) or {}
    task_type = tm.get("task_type", "unknown")
    analysis = tm.get("analysis", {}) or {}
    eye_summary = md.get("summary", {}) or {}

    # ---- Strict per-frame usable-data analysis (the core fix) ----
    fd = _frame_diagnostics(files["frames"])
    total_frames = fd["total_frames"]
    usable_frames = fd["usable_eye_tracking_frames"]
    usable_percent = round(100.0 * usable_frames / total_frames, 1) if total_frames else None
    avg_confidence = fd["average_confidence"]

    # ---- Trial counts (task-aware) ----
    file_total, file_valid = _trial_counts(files["trials"], task_type)
    if task_type == "smooth_pursuit":
        total_trials = int(analysis.get("total_cycles") or file_total)
        valid_trials = int(analysis.get("valid_cycles", file_valid) or 0)
    else:
        total_trials = int(analysis.get("total_trials") or file_total)
        valid_trials = int(analysis.get("response_count", file_valid) or 0)
    unclear_trials = max(0, total_trials - valid_trials)

    # ---- Quality label (usable% + confidence + valid ratio) ----
    label = quality_label(usable_percent, avg_confidence, valid_trials, total_trials)

    # ---- Blink count (from eye metadata; never invented) ----
    blink_count = eye_summary.get("blink_count")

    # ---- Per-task metrics + headline RT (null when unmeasured) ----
    task_metrics, rounds_completed, avg_rt = _build_task_metrics(
        task_type, analysis, total_trials, valid_trials
    )

    # ---- Diagnostics ----
    diagnostics: Dict[str, Any] = {
        "total_frames_received": total_frames,
        "total_frames_processed": total_frames,
        "frames_with_face_detected": fd["frames_with_face_detected"],
        "frames_with_eye_detected": fd["frames_with_eye_detected"],
        "frames_with_pupil_or_gaze_detected": fd["frames_with_pupil_or_gaze_detected"],
        "usable_eye_tracking_frames": usable_frames,
        "usable_eye_tracking_percent": usable_percent,
        "gaze_samples_available": fd["frames_with_pupil_or_gaze_detected"],
        "average_confidence": avg_confidence,
        "total_trials": total_trials,
        "valid_trials": valid_trials,
        "unclear_trials": unclear_trials,
        "bad_trials": 0,
        "task_events_received": None,
        "target_onset_events_received": None,
        "missing_gaze_reason_counts": fd["missing_gaze_reason_counts"],
        "main_unclear_reason": fd["main_unclear_reason"],
    }
    if extra_diagnostics:
        diagnostics.update({k: v for k, v in extra_diagnostics.items() if v is not None})

    notes = None
    if valid_trials == 0 and total_trials > 0:
        notes = "No clear eye-movement responses were detected in this session."

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
        "average_confidence": avg_confidence,
        "blink_count": int(blink_count) if blink_count is not None else None,
        "rounds_completed": rounds_completed,
        "average_response_time_ms": avg_rt,
        "task_metrics": task_metrics,
        "diagnostics": diagnostics,
        "notes": notes,
        "recommendations": _recommendations(usable_percent, valid_trials, total_trials, blink_count),
        "exports": existing_exports(session_id, sessions_dir),
        "disclaimer": DISCLAIMER,
    }
    return summary


# ---------------------------------------------------------------------------
# Per-task metric shaping (task-appropriate fields only; None when unmeasured)
# ---------------------------------------------------------------------------

def _build_task_metrics(task_type: str, a: Dict[str, Any], total: int, valid: int):
    unclear = max(0, total - valid)

    if task_type == "prosaccade":
        metrics = {
            "average_response_time_ms": a.get("mean_latency_ms"),
            "fastest_response_ms": a.get("min_latency_ms"),
            "successful_clear_rounds": a.get("correct_count", 0),
            "unclear_rounds": unclear,
            "rounds_with_response_percent": _pct(a.get("response_rate")),
            "average_eye_movement_speed_px_per_sec": a.get("mean_peak_velocity_px_per_sec"),
        }
        return metrics, total, a.get("mean_latency_ms")

    if task_type == "antisaccade":
        metrics = {
            "correct_direction_rounds": a.get("correct_count", 0),
            "average_response_time_ms": a.get("mean_correct_latency_ms"),
            "self_corrections": a.get("correction_count", 0),
            "looked_toward_first_percent": _pct(a.get("error_rate")),
            "unclear_rounds": unclear,
        }
        return metrics, total, a.get("mean_correct_latency_ms")

    if task_type == "gap_overlap":
        metrics = {
            "average_response_time_gap_ms": a.get("mean_gap_latency_ms"),
            "average_response_time_overlap_ms": a.get("mean_overlap_latency_ms"),
            "gap_effect_ms": a.get("gap_effect_ms"),
            "valid_gap_rounds": a.get("gap_response_count", 0),
            "valid_overlap_rounds": a.get("overlap_response_count", 0),
            "gap_rounds": a.get("gap_trials", 0),
            "overlap_rounds": a.get("overlap_trials", 0),
        }
        rts = [v for v in (a.get("mean_gap_latency_ms"), a.get("mean_overlap_latency_ms")) if v is not None]
        avg = round(sum(rts) / len(rts), 1) if rts else None
        return metrics, total, avg

    if task_type == "smooth_pursuit":
        metrics = {
            "tracking_gain": a.get("mean_pursuit_gain"),
            "average_tracking_difference_px": a.get("mean_position_error_px"),
            "time_tracking_clear_percent": _pct(a.get("mean_time_on_target")),
            "catch_up_eye_movements": a.get("total_catch_up_saccades", 0),
            "valid_cycles": a.get("valid_cycles", valid),
        }
        return metrics, a.get("total_cycles", total), None

    return {}, total, None


# ---------------------------------------------------------------------------
# Frame-level diagnostics (the real usable-data calculation)
# ---------------------------------------------------------------------------

def _frame_diagnostics(path: Path) -> Dict[str, Any]:
    out = {
        "total_frames": 0,
        "frames_with_face_detected": 0,
        "frames_with_eye_detected": 0,
        "frames_with_pupil_or_gaze_detected": 0,
        "usable_eye_tracking_frames": 0,
        "average_confidence": None,
        "missing_gaze_reason_counts": {},
        "main_unclear_reason": None,
    }
    if not path.exists():
        return out

    reasons: Counter = Counter()
    conf_sum = 0.0
    conf_n = 0
    try:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                out["total_frames"] += 1
                face = _truthy(row.get("face_detected"))
                eye = _truthy(row.get("left_eye_detected")) or _truthy(row.get("right_eye_detected"))
                pupil = _truthy(row.get("left_pupil_detected")) or _truthy(row.get("right_pupil_detected"))
                blink = _truthy(row.get("blink_detected"))
                quality = (row.get("frame_quality") or "").strip().lower()
                conf = _to_float(row.get("confidence_score"))

                if face:
                    out["frames_with_face_detected"] += 1
                    conf_sum += conf
                    conf_n += 1
                if face and eye:
                    out["frames_with_eye_detected"] += 1
                if pupil:
                    out["frames_with_pupil_or_gaze_detected"] += 1

                usable = (
                    face and eye and pupil
                    and conf >= USABLE_CONFIDENCE_THRESHOLD
                    and quality != "bad"
                    and not blink
                )
                if usable:
                    out["usable_eye_tracking_frames"] += 1
                else:
                    reasons[_unusable_reason(face, eye, pupil, blink, quality, conf)] += 1
    except Exception:  # noqa: BLE001
        logger.warning("Could not read frames CSV: %s", path)
        return out

    out["average_confidence"] = round(conf_sum / conf_n, 3) if conf_n else None
    out["missing_gaze_reason_counts"] = dict(reasons)
    out["main_unclear_reason"] = reasons.most_common(1)[0][0] if reasons else None
    return out


def _unusable_reason(face, eye, pupil, blink, quality, conf) -> str:
    if not face:
        return "no_face"
    if blink:
        return "blink"
    if quality == "bad":
        return "bad_quality"
    if not eye:
        return "no_eye"
    if not pupil:
        return "no_pupil_or_gaze"
    if conf < USABLE_CONFIDENCE_THRESHOLD:
        return "low_confidence"
    return "other"


def _trial_counts(path: Path, task_type: str) -> Tuple[int, int]:
    """Return (total_trials, valid_trials) from trials.csv."""
    if not path.exists():
        return 0, 0
    total = valid = 0
    try:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                total += 1
                if task_type == "smooth_pursuit":
                    if _to_float(row.get("mean_pursuit_gain")) > 0 or _to_float(row.get("mean_position_error_px")) > 0:
                        valid += 1
                else:
                    if _truthy(row.get("response_detected")):
                        valid += 1
    except Exception:  # noqa: BLE001
        return total, valid
    return total, valid


# ---------------------------------------------------------------------------
# Recommendations (research-only, friendly)
# ---------------------------------------------------------------------------

def _recommendations(usable: Optional[float], valid_trials: int,
                     total_trials: int, blinks: Optional[int]) -> List[str]:
    recs: List[str] = []
    if total_trials > 0 and valid_trials == 0:
        recs.append("No clear eye movements were captured. Sit a little closer and face the camera squarely.")
        recs.append("Even, front-on lighting on your face helps the camera see your eyes.")
    elif usable is None or usable < 60:
        recs.append("Tracking was limited. Try sitting a little closer to the camera.")
        recs.append("Better, even lighting on your face may improve tracking.")
    elif usable < 80:
        recs.append("Tracking was usable. Keeping your head centered and still helps next time.")
    else:
        recs.append("The session had enough clear data for review.")

    if blinks and blinks > 40:
        recs.append("Frequent blinking was detected — resting your eyes beforehand can help.")

    return recs[:3]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _truthy(v: Any) -> bool:
    return str(v).strip() in ("1", "True", "true", "TRUE")


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


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
    """Convert a 0–1 ratio to a 0–100 percent, preserving None (never 0 for missing)."""
    if ratio is None:
        return None
    return round(float(ratio) * 100, 1)
