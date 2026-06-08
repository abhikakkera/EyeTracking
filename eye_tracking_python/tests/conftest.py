"""
Shared pytest fixtures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Make project root importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import AppConfig
from src.data.schema import (
    EyeRegionData, FrameRecord, FrameQuality,
    DetectionMethod, SessionMetadata, TestType,
)


@pytest.fixture()
def config() -> AppConfig:
    """Default application config for tests."""
    return AppConfig()


@pytest.fixture()
def blank_eye_roi() -> np.ndarray:
    """A 120×60 blank (gray) eye ROI image."""
    return np.full((60, 120, 3), 128, dtype=np.uint8)


@pytest.fixture()
def synthetic_pupil_roi() -> np.ndarray:
    """
    A 120×60 eye ROI with a synthetic dark circular pupil at the centre.
    Used to test pupil detection without a real camera.
    """
    img = np.full((60, 120, 3), 180, dtype=np.uint8)
    # Draw a dark circle (pupil) at the centre
    center = (60, 30)
    radius = 12
    import cv2
    cv2.circle(img, center, radius, (30, 30, 30), -1)
    # Draw a lighter circle around it (iris-ish)
    cv2.circle(img, center, radius + 8, (100, 100, 100), 2)
    return img


@pytest.fixture()
def mock_eye_region(synthetic_pupil_roi) -> EyeRegionData:
    """EyeRegionData wrapping the synthetic pupil ROI."""
    return EyeRegionData(
        detected=True,
        roi_image=synthetic_pupil_roi,
        roi_x=200,
        roi_y=150,
        roi_w=120,
        roi_h=60,
        ear=0.35,
        is_open=True,
        confidence=0.9,
    )


@pytest.fixture()
def sample_frame_record() -> FrameRecord:
    return FrameRecord(
        session_id="test-session",
        frame_number=42,
        timestamp_sec=1.4,
        face_detected=True,
        left_eye_detected=True,
        right_eye_detected=True,
        left_pupil_detected=True,
        right_pupil_detected=True,
        left_pupil_x=320.0,
        left_pupil_y=240.0,
        right_pupil_x=420.0,
        right_pupil_y=238.0,
        left_pupil_diameter_px=22.5,
        right_pupil_diameter_px=21.8,
        left_norm_x=0.45,
        left_norm_y=0.48,
        right_norm_x=0.52,
        right_norm_y=0.50,
        gaze_x=0.485,
        gaze_y=0.49,
        blink_detected=False,
        left_ear=0.32,
        right_ear=0.31,
        confidence_score=0.88,
        frame_quality=FrameQuality.GOOD,
        left_detection_method=DetectionMethod.CONTOUR_ELLIPSE,
        right_detection_method=DetectionMethod.CONTOUR_ELLIPSE,
    )
