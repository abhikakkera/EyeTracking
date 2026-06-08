"""
Frame processor — decodes a browser-streamed JPEG frame and runs it through the
EXISTING Python eye tracker (no OpenCV window).

This is the bridge that lets the in-browser web task mode reuse the full
pupil/iris/quality/distance pipeline that the CLI mode uses.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from src.data.schema import FrameData, FrameRecord

logger = logging.getLogger(__name__)


def decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    """Decode JPEG/PNG bytes into a BGR numpy image (or None on failure)."""
    if not data:
        return None
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # → BGR
    return img


def run_tracker(
    tracker,
    image_bgr: np.ndarray,
    frame_number: int,
    timestamp_sec: float,
    fps: float,
) -> FrameRecord:
    """
    Feed one frame to the EyeTracker exactly like the camera loop would.

    timestamp_sec MUST be strictly increasing across calls for the same tracker
    (MediaPipe VIDEO mode); the caller is responsible for monotonicity.
    """
    h, w = image_bgr.shape[:2]
    fd = FrameData(
        image=image_bgr,
        frame_number=frame_number,
        timestamp_sec=timestamp_sec,
        wall_clock=time.time(),
        fps=fps,
        width=w,
        height=h,
        source="web",
    )
    return tracker.process_frame(fd)


def live_guidance(record: FrameRecord) -> Tuple[str, str, str]:
    """
    Map a FrameRecord into (tracking_status, distance_status, friendly message)
    for display in the website. Friendly, non-clinical language only.
    """
    tracking_status = record.frame_quality.value  # good | questionable | bad
    distance_status = record.camera_distance_status or "unknown"

    if not record.face_detected:
        return tracking_status, distance_status, "I'm having trouble seeing your eyes clearly."

    if distance_status == "too_close":
        return tracking_status, distance_status, "Move a little farther back."
    if distance_status == "too_far":
        return tracking_status, distance_status, "Move a little closer."

    flags = record.quality_flags or []
    if "low_light" in flags:
        return tracking_status, distance_status, "Try adding more light."
    if "overexposed" in flags:
        return tracking_status, distance_status, "That's a bit bright — try softer lighting."

    if record.blink_detected:
        return tracking_status, distance_status, "Keep your eyes open and relaxed."

    if tracking_status == "good":
        return tracking_status, distance_status, "Great — your eyes are clear."
    if tracking_status == "questionable":
        return tracking_status, distance_status, "Hold still for a moment."
    return tracking_status, distance_status, "Center your face in the view."
