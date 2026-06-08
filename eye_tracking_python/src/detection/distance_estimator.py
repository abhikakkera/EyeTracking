"""
Camera-distance quality estimator — v0.3.

Estimates whether the participant is too close, too far, or well-positioned
for reliable tracking.  Uses only relative frame metrics (no real-world
distance measurement, no camera intrinsics required):

  • face bbox width / frame width
  • face bbox height / frame height
  • inter-eye distance in pixels
  • eye ROI width in pixels (from EyeRegionDetector output)

A hysteresis buffer prevents the status from flickering when the participant
is near a threshold.

Usage (called from EyeTracker._process_frame_inner):
    result = self._distance_estimator.assess(
        face, left_eye, right_eye, img_w, img_h
    )
    record.camera_distance_status  = result.status
    record.camera_distance_score   = result.score
    ...
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque

from config import AppConfig
from src.data.schema import EyeRegionData, FaceData

logger = logging.getLogger(__name__)

# Status string constants (kept as plain strings to avoid adding another
# Enum dependency; values match what gets written to FrameRecord and CSV).
STATUS_GOOD      = "good"
STATUS_TOO_CLOSE = "too_close"
STATUS_TOO_FAR   = "too_far"
STATUS_UNKNOWN   = "unknown"


@dataclass
class DistanceEstimationResult:
    """Per-frame result from DistanceEstimator.assess()."""
    status: str = STATUS_UNKNOWN
    score: float = 0.0              # 0–1; 1.0 = perfectly centered in good range
    guidance_message: str = ""
    face_bbox_width_ratio: float = 0.0
    face_bbox_height_ratio: float = 0.0
    inter_eye_distance_px: float = 0.0
    left_eye_roi_width: int = 0
    right_eye_roi_width: int = 0


class DistanceEstimator:
    """
    Estimates camera-distance quality and guidance message.

    Results are smoothed via a rolling hysteresis buffer so the displayed
    status changes only after `hysteresis_frames` consecutive frames agree
    on the new status.
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.camera_distance
        self._buf: Deque[str] = deque(maxlen=self._cfg.hysteresis_frames)
        self._last_status: str = STATUS_UNKNOWN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        face: FaceData,
        left_eye: EyeRegionData,
        right_eye: EyeRegionData,
        frame_w: int,
        frame_h: int,
    ) -> DistanceEstimationResult:
        """
        Assess distance quality for one frame.

        Parameters
        ----------
        face      : FaceData from FaceDetector
        left_eye  : EyeRegionData for left eye (may be undetected)
        right_eye : EyeRegionData for right eye (may be undetected)
        frame_w   : frame width in pixels
        frame_h   : frame height in pixels

        Returns
        -------
        DistanceEstimationResult with hysteresis-smoothed status.
        """
        if not face.detected:
            self._buf.append(STATUS_UNKNOWN)
            smoothed = self._smooth()
            return DistanceEstimationResult(
                status=smoothed,
                score=0.0,
                guidance_message="Position your face in the camera view.",
            )

        # --- Compute raw metrics ---
        face_w_ratio = face.bbox_w / max(frame_w, 1)
        face_h_ratio = face.bbox_h / max(frame_h, 1)

        # Inter-eye distance: centre of left ROI vs centre of right ROI.
        # Both may be undetected on a bad frame; handle gracefully.
        inter_eye_px = 0.0
        if left_eye.detected and right_eye.detected:
            lcx = left_eye.roi_x + left_eye.roi_w / 2.0
            rcx = right_eye.roi_x + right_eye.roi_w / 2.0
            inter_eye_px = abs(rcx - lcx)

        left_roi_w  = left_eye.roi_w  if left_eye.detected  else 0
        right_roi_w = right_eye.roi_w if right_eye.detected else 0

        # --- Raw status decision ---
        raw_status = self._classify(face_w_ratio, face_h_ratio,
                                    inter_eye_px, left_roi_w, right_roi_w)
        self._buf.append(raw_status)
        smoothed = self._smooth()

        # --- Quality score ---
        score = self._compute_score(face_w_ratio, inter_eye_px)

        # --- Guidance message ---
        msg = _GUIDANCE[smoothed]

        return DistanceEstimationResult(
            status=smoothed,
            score=score,
            guidance_message=msg,
            face_bbox_width_ratio=round(face_w_ratio, 4),
            face_bbox_height_ratio=round(face_h_ratio, 4),
            inter_eye_distance_px=round(inter_eye_px, 1),
            left_eye_roi_width=left_roi_w,
            right_eye_roi_width=right_roi_w,
        )

    def reset(self) -> None:
        """Clear hysteresis buffer (call between sessions)."""
        self._buf.clear()
        self._last_status = STATUS_UNKNOWN

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify(
        self,
        face_w_ratio: float,
        face_h_ratio: float,
        inter_eye_px: float,
        left_roi_w: int,
        right_roi_w: int,
    ) -> str:
        cfg = self._cfg

        # Too close: face fills too much of the frame
        if face_w_ratio > cfg.max_face_width_ratio:
            return STATUS_TOO_CLOSE
        if face_h_ratio > cfg.max_face_height_ratio:
            return STATUS_TOO_CLOSE

        # Too far: face is tiny, eyes are hard to track
        if face_w_ratio < cfg.min_face_width_ratio:
            return STATUS_TOO_FAR
        if inter_eye_px > 0 and inter_eye_px < cfg.min_inter_eye_distance_px:
            return STATUS_TOO_FAR
        min_roi = min(r for r in (left_roi_w, right_roi_w) if r > 0) if (left_roi_w or right_roi_w) else 0
        if min_roi > 0 and min_roi < cfg.min_eye_roi_width_px:
            return STATUS_TOO_FAR

        return STATUS_GOOD

    def _smooth(self) -> str:
        """
        Return hysteresis-smoothed status.
        Only change the displayed status when all frames in the buffer agree.
        """
        if not self._buf:
            return STATUS_UNKNOWN
        # All frames in buffer must agree on the new status
        if len(set(self._buf)) == 1:
            self._last_status = self._buf[-1]
        return self._last_status

    def _compute_score(self, face_w_ratio: float, inter_eye_px: float) -> float:
        """
        Score 0–1: how centred the participant is in the good range.
        1.0 = midpoint of good range; decays toward boundaries.
        """
        cfg = self._cfg
        good_min = cfg.min_face_width_ratio
        good_max = cfg.max_face_width_ratio
        if face_w_ratio < good_min or face_w_ratio > good_max:
            return max(0.0, 1.0 - abs(face_w_ratio - (good_min + good_max) / 2) * 3)

        # Linear score within good range: 1.0 at midpoint
        mid = (good_min + good_max) / 2.0
        half_range = (good_max - good_min) / 2.0
        score = 1.0 - abs(face_w_ratio - mid) / half_range
        return round(max(0.0, min(1.0, score)), 3)


_GUIDANCE: dict[str, str] = {
    STATUS_GOOD:      "",
    STATUS_TOO_CLOSE: "Move slightly farther from the camera.",
    STATUS_TOO_FAR:   "Move closer to the camera for better tracking.",
    STATUS_UNKNOWN:   "Position your face in the camera view.",
}
