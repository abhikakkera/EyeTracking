"""
Frame quality assessor — v0.2 (new module).

Evaluates every frame and produces:
  - quality_score : float [0, 1]
  - quality_flags : List[str]  — human-readable problem labels
  - frame_quality : FrameQuality enum (GOOD / QUESTIONABLE / BAD)

Flags generated:
  "face_not_detected"    — MediaPipe found no face
  "eye_not_detected"     — one or both eyes missing
  "blink"                — blink state is active
  "low_light"            — eye ROI is very dark
  "overexposed"          — eye ROI is saturated
  "motion_blur"          — Laplacian variance of eye ROI is low
  "low_pupil_confidence" — best pupil confidence below threshold
  "unrealistic_jump"     — pupil moved impossibly far between frames

The quality score is the complement of a weighted penalty sum — it degrades
gracefully rather than snapping between states.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import AppConfig
from src.data.schema import EyeRegionData, FrameQuality, PupilData
from src.utils.geometry import euclidean_distance, image_blur_score

logger = logging.getLogger(__name__)


class QualityAssessor:
    """
    Stateless quality evaluator.

    Usage:
        assessor = QualityAssessor(config)
        score, flags, quality = assessor.assess(
            face_detected, left_eye, right_eye,
            left_pupil, right_pupil,
            blink_detected, prev_pupil_frame_pos,
        )
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.quality

    def assess(
        self,
        face_detected: bool,
        left_eye: EyeRegionData,
        right_eye: EyeRegionData,
        left_pupil: PupilData,
        right_pupil: PupilData,
        blink_detected: bool,
        prev_center_frame: Optional[Tuple[float, float]] = None,
        current_center_frame: Optional[Tuple[float, float]] = None,
    ) -> Tuple[float, List[str], FrameQuality]:
        """
        Evaluate frame quality.

        Returns
        -------
        score : float [0, 1] — higher is better
        flags : list of string labels
        quality : FrameQuality enum
        """
        flags: List[str] = []
        penalty = 0.0

        # --- Face detection --------------------------------------------------
        if not face_detected:
            flags.append("face_not_detected")
            penalty += 0.50
            # Can't evaluate anything else meaningfully
            score = max(0.0, 1.0 - penalty)
            return score, flags, self._classify(score)

        # --- Eye detection ---------------------------------------------------
        left_ok = left_eye.detected
        right_ok = right_eye.detected
        if not left_ok and not right_ok:
            flags.append("eye_not_detected")
            penalty += 0.40
        elif not left_ok or not right_ok:
            flags.append("eye_not_detected")
            penalty += 0.15

        # --- Blink -----------------------------------------------------------
        if blink_detected:
            flags.append("blink")
            penalty += 0.30

        # --- Lighting (computed on eye ROI if available) ---------------------
        for eye_region in [left_eye, right_eye]:
            if eye_region.detected and eye_region.roi_image is not None:
                roi_gray = cv2.cvtColor(
                    eye_region.roi_image, cv2.COLOR_BGR2GRAY
                )
                mean_val = float(np.mean(roi_gray))
                blur_val = image_blur_score(roi_gray)

                if mean_val < self._cfg.low_light_threshold:
                    if "low_light" not in flags:
                        flags.append("low_light")
                    penalty += 0.15

                if mean_val > self._cfg.overexposed_threshold:
                    if "overexposed" not in flags:
                        flags.append("overexposed")
                    penalty += 0.10

                if blur_val < self._cfg.blur_threshold:
                    if "motion_blur" not in flags:
                        flags.append("motion_blur")
                    penalty += 0.15
                break  # one eye is sufficient for lighting assessment

        # --- Pupil confidence ------------------------------------------------
        best_pupil_conf = max(
            left_pupil.confidence if left_pupil.detected else 0.0,
            right_pupil.confidence if right_pupil.detected else 0.0,
        )
        if best_pupil_conf < self._cfg.min_pupil_confidence:
            flags.append("low_pupil_confidence")
            penalty += 0.20

        # --- Unrealistic jump ------------------------------------------------
        if (
            prev_center_frame is not None
            and current_center_frame is not None
        ):
            jump = euclidean_distance(prev_center_frame, current_center_frame)
            if jump > self._cfg.unrealistic_jump_px:
                flags.append("unrealistic_jump")
                penalty += 0.25

        score = max(0.0, min(1.0, 1.0 - penalty))
        return score, flags, self._classify(score)

    @staticmethod
    def _classify(score: float) -> FrameQuality:
        if score >= 0.65:
            return FrameQuality.GOOD
        if score >= 0.35:
            return FrameQuality.QUESTIONABLE
        return FrameQuality.BAD
