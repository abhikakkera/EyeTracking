"""
Unit tests for the pupil detector.

These tests use synthetic images — no webcam or display required.
The synthetic image contains a high-contrast dark circle (the "pupil") on a
lighter background, which the detector should reliably find.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from config import AppConfig
from src.data.schema import DetectionMethod
from src.detection.pupil_detector import PupilDetector


@pytest.fixture()
def detector(config: AppConfig) -> PupilDetector:
    return PupilDetector(config)


def _make_synthetic_roi(
    width: int = 120,
    height: int = 60,
    pupil_center: tuple = (60, 30),
    pupil_radius: int = 12,
    bg_intensity: int = 160,
    pupil_intensity: int = 20,
) -> np.ndarray:
    """Create a synthetic eye ROI with a dark circular pupil."""
    img = np.full((height, width, 3), bg_intensity, dtype=np.uint8)
    cv2.circle(img, pupil_center, pupil_radius, (pupil_intensity,) * 3, -1)
    # Add a slightly lighter iris ring
    cv2.circle(img, pupil_center, pupil_radius + 8, (100,) * 3, 2)
    return img


def _make_eye_region(roi_img, roi_x=200, roi_y=150):
    from src.data.schema import EyeRegionData
    return EyeRegionData(
        detected=True,
        roi_image=roi_img,
        roi_x=roi_x,
        roi_y=roi_y,
        roi_w=roi_img.shape[1],
        roi_h=roi_img.shape[0],
        ear=0.32,
        is_open=True,
        confidence=0.9,
    )


class TestPupilDetectorSyntheticInput:
    def test_detects_synthetic_pupil(self, detector):
        roi = _make_synthetic_roi()
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        assert result.detected, "Detector should find the synthetic pupil"

    def test_pupil_center_is_near_actual_center(self, detector):
        roi = _make_synthetic_roi(pupil_center=(60, 30))
        eye = _make_eye_region(roi, roi_x=200, roi_y=150)
        result = detector.detect(eye)
        if result.detected:
            # In frame coords: expected ≈ (200+60, 150+30) = (260, 180)
            assert abs(result.center_frame[0] - 260) < 20, "X too far from expected"
            assert abs(result.center_frame[1] - 180) < 20, "Y too far from expected"

    def test_pupil_radius_reasonable(self, detector):
        roi = _make_synthetic_roi(pupil_radius=12)
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        if result.detected:
            # Radius should be in the neighbourhood of 12 px (normalised ROI space)
            assert 5 < result.radius_px < 30

    def test_empty_roi_returns_not_detected(self, detector):
        from src.data.schema import EyeRegionData
        result = detector.detect(EyeRegionData())
        assert not result.detected

    def test_none_roi_returns_not_detected(self, detector):
        from src.data.schema import EyeRegionData
        eye = EyeRegionData(detected=True, roi_image=None)
        result = detector.detect(eye)
        assert not result.detected

    def test_blank_roi_confidence_low(self, detector):
        """A uniform gray image has no pupil — confidence should be low."""
        roi = np.full((60, 120, 3), 128, dtype=np.uint8)
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        # Either not detected or low confidence
        assert not result.detected or result.confidence < 0.4

    def test_confidence_bounded(self, detector):
        roi = _make_synthetic_roi()
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        assert 0.0 <= result.confidence <= 1.0

    def test_detection_method_is_set(self, detector):
        roi = _make_synthetic_roi()
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        if result.detected:
            assert result.method != DetectionMethod.NONE

    def test_pupil_off_center(self, detector):
        """Detector should find a pupil that is not at the ROI centre."""
        roi = _make_synthetic_roi(pupil_center=(30, 20))
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        assert result.detected

    def test_temporal_prediction_after_reset(self, detector):
        """After reset, no temporal prediction should be available."""
        detector.reset()
        from src.data.schema import EyeRegionData
        result = detector.detect(EyeRegionData())
        assert not result.detected

    def test_diameter_equals_two_times_radius(self, detector):
        roi = _make_synthetic_roi()
        eye = _make_eye_region(roi)
        result = detector.detect(eye)
        if result.detected and result.radius_px > 0:
            assert result.diameter_px == pytest.approx(result.radius_px * 2, rel=0.05)
