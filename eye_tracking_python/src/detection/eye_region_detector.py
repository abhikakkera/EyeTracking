"""
Eye region extractor.

Given the full-frame image and face landmarks from MediaPipe, this module
crops each eye ROI, computes the Eye Aspect Ratio (EAR), and normalises the
ROI to a fixed size for downstream pupil detection.

Landmark index conventions follow face_detector.py:
    Viewer's LEFT eye  = subject's RIGHT = MediaPipe right-eye family (33..246)
    Viewer's RIGHT eye = subject's LEFT  = MediaPipe left-eye  family (362..398)
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import AppConfig
from src.data.schema import EyeRegionData, FaceData
from src.utils.geometry import eye_aspect_ratio

logger = logging.getLogger(__name__)

# Six-point landmark indices used for EAR calculation (Soukupova & Cech 2016)
# Format: [left_corner, upper_left, upper_right, right_corner, lower_right, lower_left]
_LEFT_EAR_IDX = [33, 160, 158, 133, 153, 144]   # viewer's left eye
_RIGHT_EAR_IDX = [362, 385, 387, 263, 373, 380]  # viewer's right eye

# All landmark indices that define each eye's boundary (for ROI computation)
_LEFT_EYE_ALL_IDX = [
    33, 7, 163, 144, 145, 153, 154, 155, 133,
    173, 157, 158, 159, 160, 161, 246,
]
_RIGHT_EYE_ALL_IDX = [
    362, 382, 381, 380, 374, 373, 390, 249, 263,
    466, 388, 387, 386, 385, 384, 398,
]


class EyeRegionDetector:
    """
    Extracts and normalises left and right eye regions from a face frame.

    Usage:
        detector = EyeRegionDetector(config)
        left, right = detector.extract(bgr_frame, face_data)
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.detection

    def extract(
        self,
        bgr_frame: np.ndarray,
        face_data: FaceData,
    ) -> Tuple[EyeRegionData, EyeRegionData]:
        """
        Extract left and right eye regions.

        Returns:
            (left_eye, right_eye) — EyeRegionData for each eye.
            If the face was not detected or landmarks are missing,
            both will have detected=False.
        """
        if not face_data.detected or not face_data.landmarks:
            return EyeRegionData(), EyeRegionData()

        h, w = bgr_frame.shape[:2]
        landmarks = face_data.landmarks

        left = self._extract_one(bgr_frame, landmarks, _LEFT_EYE_ALL_IDX, _LEFT_EAR_IDX, w, h)
        right = self._extract_one(bgr_frame, landmarks, _RIGHT_EYE_ALL_IDX, _RIGHT_EAR_IDX, w, h)
        return left, right

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_one(
        self,
        bgr_frame: np.ndarray,
        landmarks: List[Tuple[float, float]],
        eye_idx: List[int],
        ear_idx: List[int],
        frame_w: int,
        frame_h: int,
    ) -> EyeRegionData:
        try:
            # Guard: landmark indices must be in range
            max_needed = max(max(eye_idx), max(ear_idx))
            if max_needed >= len(landmarks):
                return EyeRegionData()

            eye_pts = [landmarks[i] for i in eye_idx]
            ear_pts = [landmarks[i] for i in ear_idx]

            # Bounding box of eye landmarks
            xs = [p[0] for p in eye_pts]
            ys = [p[1] for p in eye_pts]
            x_min = max(0, int(min(xs)))
            y_min = max(0, int(min(ys)))
            x_max = min(frame_w, int(max(xs)))
            y_max = min(frame_h, int(max(ys)))

            # Add padding
            eye_w = x_max - x_min
            eye_h = y_max - y_min
            if eye_w < 4 or eye_h < 2:
                return EyeRegionData()

            pad_x = int(eye_w * self._cfg.eye_roi_padding)
            pad_y = int(eye_h * self._cfg.eye_roi_padding)
            x_min = max(0, x_min - pad_x)
            y_min = max(0, y_min - pad_y)
            x_max = min(frame_w, x_max + pad_x)
            y_max = min(frame_h, y_max + pad_y)

            roi_w = x_max - x_min
            roi_h = y_max - y_min
            if roi_w < 4 or roi_h < 2:
                return EyeRegionData()

            # Crop and normalise to fixed size
            crop = bgr_frame[y_min:y_max, x_min:x_max]
            roi_normalised = cv2.resize(
                crop,
                (self._cfg.eye_roi_width, self._cfg.eye_roi_height),
                interpolation=cv2.INTER_LINEAR,
            )

            # EAR
            ear_landmarks = [landmarks[i] for i in ear_idx]
            ear = eye_aspect_ratio(ear_landmarks)
            is_open = ear > 0.0  # blink detector uses a stricter threshold

            return EyeRegionData(
                detected=True,
                roi_image=roi_normalised,
                roi_x=x_min,
                roi_y=y_min,
                roi_w=roi_w,
                roi_h=roi_h,
                landmarks_frame=ear_landmarks,
                ear=ear,
                is_open=is_open,
                confidence=0.9,
            )

        except Exception as exc:  # noqa: BLE001
            logger.debug("Eye region extraction failed: %s", exc)
            return EyeRegionData()
