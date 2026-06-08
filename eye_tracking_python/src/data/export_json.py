"""
JSON export for session metadata and event summaries.

Writes:
    <output_dir>/<session_id>_metadata.json   — session metadata + summary stats
    <output_dir>/<session_id>_events.json     — all blink/saccade/fixation events

Frame-level data is exported separately via export_csv.py because JSON frame
arrays become very large (30 fps × 60 s = 1800 objects).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import List

from src.data.session_recorder import SessionData

logger = logging.getLogger(__name__)


def export_session(session: SessionData, output_dir: str | Path) -> List[Path]:
    """
    Write JSON metadata and events files.
    Returns a list of the paths written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sid = session.metadata.session_id[:16]

    written: List[Path] = []
    written.append(_write_metadata(session, out / f"{sid}_metadata.json"))
    written.append(_write_events(session, out / f"{sid}_events.json"))

    logger.info("JSON export complete: %s", out)
    return written


def _write_metadata(session: SessionData, path: Path) -> Path:
    meta = session.metadata
    frames = session.frames

    # Compute basic summary statistics
    good = [f for f in frames if f.frame_quality.value == "good"]
    blink_durs = [e.duration_ms for e in session.blinks]
    sac_amps = [e.amplitude_px for e in session.saccades]
    sac_vels = [e.peak_velocity_px_per_sec for e in session.saccades]
    fix_durs = [e.duration_ms for e in session.fixations]
    velocities = [f.gaze_velocity_px_per_sec for f in frames if f.face_detected]

    doc = {
        "session_id": meta.session_id,
        "subject_id": meta.subject_id,
        "software_version": meta.software_version,
        "timestamp_start": meta.timestamp_start,
        "timestamp_end": meta.timestamp_end,
        "duration_sec": round(meta.timestamp_end - meta.timestamp_start, 2),
        "camera_type": meta.camera_type,
        "camera_resolution": list(meta.camera_resolution),
        "fps": round(meta.fps, 2),
        "test_type": meta.test_type.value,
        "calibration_used": meta.calibration_used,
        "calibration_points": meta.calibration_points,
        "notes": meta.notes,
        "summary": {
            "total_frames": meta.total_frames,
            "good_frames": meta.good_frames,
            "good_frame_ratio": round(meta.good_frames / max(meta.total_frames, 1), 3),
            "blink_count": meta.blink_count,
            "saccade_count": meta.saccade_count,
            "fixation_count": meta.fixation_count,
            "mean_blink_duration_ms": _safe_mean(blink_durs),
            "mean_saccade_amplitude_px": _safe_mean(sac_amps),
            "mean_saccade_velocity_px_per_sec": _safe_mean(sac_vels),
            "peak_saccade_velocity_px_per_sec": max(sac_vels) if sac_vels else 0.0,
            "mean_fixation_duration_ms": _safe_mean(fix_durs),
            "mean_gaze_velocity_px_per_sec": _safe_mean(velocities),
        },
        "disclaimer": (
            "This software is a research prototype for eye-tracking data collection. "
            "It does NOT diagnose, treat, or predict Parkinson's disease or any other "
            "medical condition. Any clinical use requires medical validation, regulatory "
            "review, and oversight by qualified healthcare professionals."
        ),
    }

    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, default=str)
    return path


def _write_events(session: SessionData, path: Path) -> Path:
    doc = {
        "session_id": session.metadata.session_id,
        "blinks": [
            {
                "start_sec": round(e.start_timestamp_sec, 4),
                "end_sec": round(e.end_timestamp_sec, 4),
                "duration_ms": round(e.duration_ms, 2),
                "eye": e.affected_eye,
                "confidence": round(e.confidence, 4),
            }
            for e in session.blinks
        ],
        "saccades": [
            {
                "start_sec": round(e.start_timestamp_sec, 4),
                "end_sec": round(e.end_timestamp_sec, 4),
                "duration_ms": round(e.duration_ms, 2),
                "amplitude_px": round(e.amplitude_px, 2),
                "peak_velocity_px_per_sec": round(e.peak_velocity_px_per_sec, 2),
                "direction_deg": round(e.direction_deg, 2),
                "start": [round(e.start_x, 4), round(e.start_y, 4)],
                "end": [round(e.end_x, 4), round(e.end_y, 4)],
            }
            for e in session.saccades
        ],
        "fixations": [
            {
                "start_sec": round(e.start_timestamp_sec, 4),
                "end_sec": round(e.end_timestamp_sec, 4),
                "duration_ms": round(e.duration_ms, 2),
                "center": [round(e.center_x, 4), round(e.center_y, 4)],
                "dispersion_px": round(e.dispersion_px, 2),
            }
            for e in session.fixations
        ],
    }
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
    return path


def _safe_mean(values) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)
