"""
CSV export for frame-level tracking data — v0.3.

Changes from v0.1:
  - gaze_acceleration field renamed to gaze_acceleration_px_per_sec2
  - gaze_jerk_px_per_sec3 column added
  - quality_flags column added (pipe-separated list, e.g. "low_light|blink")
  - SaccadeEvent gains event_id + mean_velocity_px_per_sec
  - FixationEvent gains event_id + num_frames

Writes one CSV file per event type per session:
    <output_dir>/<session_id>_frames.csv
    <output_dir>/<session_id>_blinks.csv
    <output_dir>/<session_id>_saccades.csv
    <output_dir>/<session_id>_fixations.csv

All coordinate values are rounded to 4 decimal places.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List

from src.data.schema import BlinkEvent, FixationEvent, FrameRecord, SaccadeEvent
from src.data.session_recorder import SessionData

logger = logging.getLogger(__name__)


def export_session(session: SessionData, output_dir: str | Path) -> List[Path]:
    """Export all session data to CSV files. Returns list of paths written."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sid = session.metadata.session_id[:16]

    written: List[Path] = []
    written.append(_write_frames(session.frames, out / f"{sid}_frames.csv"))
    written.append(_write_blinks(session.blinks, out / f"{sid}_blinks.csv"))
    written.append(_write_saccades(session.saccades, out / f"{sid}_saccades.csv"))
    written.append(_write_fixations(session.fixations, out / f"{sid}_fixations.csv"))

    logger.info("CSV export complete: %d files in %s", len(written), out)
    return written


# ---------------------------------------------------------------------------
# Frame records
# ---------------------------------------------------------------------------

_FRAME_FIELDS = [
    "session_id", "frame_number", "timestamp_sec",
    "face_detected",
    "left_eye_detected", "right_eye_detected",
    "left_pupil_detected", "right_pupil_detected",
    "left_pupil_x", "left_pupil_y",
    "right_pupil_x", "right_pupil_y",
    "left_pupil_diameter_px", "right_pupil_diameter_px",
    "left_norm_x", "left_norm_y",
    "right_norm_x", "right_norm_y",
    "gaze_x", "gaze_y",
    "screen_x", "screen_y",
    "smooth_gaze_x", "smooth_gaze_y",
    "blink_detected",
    "left_ear", "right_ear",
    "gaze_velocity_px_per_sec",
    "gaze_acceleration_px_per_sec2",
    "gaze_jerk_px_per_sec3",
    "confidence_score", "frame_quality", "blur_score",
    "quality_flags",
    "left_detection_method", "right_detection_method",
    # v0.3 camera distance guidance
    "camera_distance_status", "camera_distance_score",
    "distance_guidance_message",
    "face_bbox_width_ratio", "face_bbox_height_ratio",
    "inter_eye_distance_px",
]


def _write_frames(records: List[FrameRecord], path: Path) -> Path:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FRAME_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "session_id": r.session_id,
                "frame_number": r.frame_number,
                "timestamp_sec": round(r.timestamp_sec, 4),
                "face_detected": int(r.face_detected),
                "left_eye_detected": int(r.left_eye_detected),
                "right_eye_detected": int(r.right_eye_detected),
                "left_pupil_detected": int(r.left_pupil_detected),
                "right_pupil_detected": int(r.right_pupil_detected),
                "left_pupil_x": _r4(r.left_pupil_x),
                "left_pupil_y": _r4(r.left_pupil_y),
                "right_pupil_x": _r4(r.right_pupil_x),
                "right_pupil_y": _r4(r.right_pupil_y),
                "left_pupil_diameter_px": _r4(r.left_pupil_diameter_px),
                "right_pupil_diameter_px": _r4(r.right_pupil_diameter_px),
                "left_norm_x": _r4(r.left_norm_x),
                "left_norm_y": _r4(r.left_norm_y),
                "right_norm_x": _r4(r.right_norm_x),
                "right_norm_y": _r4(r.right_norm_y),
                "gaze_x": _r4(r.gaze_x),
                "gaze_y": _r4(r.gaze_y),
                "screen_x": _r4(r.screen_x) if r.screen_x is not None else "",
                "screen_y": _r4(r.screen_y) if r.screen_y is not None else "",
                "smooth_gaze_x": _r4(r.smooth_gaze_x) if r.smooth_gaze_x is not None else "",
                "smooth_gaze_y": _r4(r.smooth_gaze_y) if r.smooth_gaze_y is not None else "",
                "blink_detected": int(r.blink_detected),
                "left_ear": _r4(r.left_ear),
                "right_ear": _r4(r.right_ear),
                "gaze_velocity_px_per_sec": _r4(r.gaze_velocity_px_per_sec),
                "gaze_acceleration_px_per_sec2": _r4(r.gaze_acceleration_px_per_sec2),
                "gaze_jerk_px_per_sec3": _r4(r.gaze_jerk_px_per_sec3),
                "confidence_score": _r4(r.confidence_score),
                "frame_quality": r.frame_quality.value,
                "blur_score": _r4(r.blur_score),
                "quality_flags": "|".join(r.quality_flags) if r.quality_flags else "",
                "left_detection_method": r.left_detection_method.value,
                "right_detection_method": r.right_detection_method.value,
                # v0.3
                "camera_distance_status": r.camera_distance_status,
                "camera_distance_score": _r4(r.camera_distance_score),
                "distance_guidance_message": r.distance_guidance_message,
                "face_bbox_width_ratio": _r4(r.face_bbox_width_ratio),
                "face_bbox_height_ratio": _r4(r.face_bbox_height_ratio),
                "inter_eye_distance_px": _r4(r.inter_eye_distance_px),
            })
    logger.debug("Wrote %d frame records to %s", len(records), path)
    return path


# ---------------------------------------------------------------------------
# Blink events
# ---------------------------------------------------------------------------

_BLINK_FIELDS = [
    "session_id", "event_id",
    "start_timestamp_sec", "end_timestamp_sec",
    "duration_ms", "affected_eye", "confidence",
]


def _write_blinks(events: List[BlinkEvent], path: Path) -> Path:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_BLINK_FIELDS)
        writer.writeheader()
        for e in events:
            writer.writerow({
                "session_id": e.session_id,
                "event_id": e.event_id,
                "start_timestamp_sec": _r4(e.start_timestamp_sec),
                "end_timestamp_sec": _r4(e.end_timestamp_sec),
                "duration_ms": _r2(e.duration_ms),
                "affected_eye": e.affected_eye,
                "confidence": _r4(e.confidence),
            })
    return path


# ---------------------------------------------------------------------------
# Saccade events
# ---------------------------------------------------------------------------

_SACCADE_FIELDS = [
    "session_id", "event_id",
    "start_timestamp_sec", "end_timestamp_sec",
    "duration_ms", "start_x", "start_y", "end_x", "end_y",
    "amplitude_px", "peak_velocity_px_per_sec", "mean_velocity_px_per_sec",
    "direction_deg", "confidence",
]


def _write_saccades(events: List[SaccadeEvent], path: Path) -> Path:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_SACCADE_FIELDS)
        writer.writeheader()
        for e in events:
            writer.writerow({
                "session_id": e.session_id,
                "event_id": e.event_id,
                "start_timestamp_sec": _r4(e.start_timestamp_sec),
                "end_timestamp_sec": _r4(e.end_timestamp_sec),
                "duration_ms": _r2(e.duration_ms),
                "start_x": _r4(e.start_x),
                "start_y": _r4(e.start_y),
                "end_x": _r4(e.end_x),
                "end_y": _r4(e.end_y),
                "amplitude_px": _r2(e.amplitude_px),
                "peak_velocity_px_per_sec": _r2(e.peak_velocity_px_per_sec),
                "mean_velocity_px_per_sec": _r2(e.mean_velocity_px_per_sec),
                "direction_deg": _r2(e.direction_deg),
                "confidence": _r4(e.confidence),
            })
    return path


# ---------------------------------------------------------------------------
# Fixation events
# ---------------------------------------------------------------------------

_FIXATION_FIELDS = [
    "session_id", "event_id",
    "start_timestamp_sec", "end_timestamp_sec",
    "duration_ms", "center_x", "center_y", "dispersion_px",
    "num_frames", "confidence",
]


def _write_fixations(events: List[FixationEvent], path: Path) -> Path:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIXATION_FIELDS)
        writer.writeheader()
        for e in events:
            writer.writerow({
                "session_id": e.session_id,
                "event_id": e.event_id,
                "start_timestamp_sec": _r4(e.start_timestamp_sec),
                "end_timestamp_sec": _r4(e.end_timestamp_sec),
                "duration_ms": _r2(e.duration_ms),
                "center_x": _r4(e.center_x),
                "center_y": _r4(e.center_y),
                "dispersion_px": _r2(e.dispersion_px),
                "num_frames": e.num_frames,
                "confidence": _r4(e.confidence),
            })
    return path


def _r4(v) -> float:
    if v is None:
        return ""  # type: ignore[return-value]
    return round(float(v), 4)


def _r2(v) -> float:
    return round(float(v), 2)
