"""
Tests for DistanceEstimator.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import AppConfig
from src.data.schema import EyeRegionData, FaceData
from src.detection.distance_estimator import (
    STATUS_GOOD,
    STATUS_TOO_CLOSE,
    STATUS_TOO_FAR,
    STATUS_UNKNOWN,
    DistanceEstimationResult,
    DistanceEstimator,
)

FRAME_W, FRAME_H = 1280, 720


def _make_face(w_ratio: float, h_ratio: float = 0.4) -> FaceData:
    """Build a FaceData with the given width fraction of FRAME_W."""
    return FaceData(
        detected=True,
        bbox_x=100,
        bbox_y=100,
        bbox_w=int(w_ratio * FRAME_W),
        bbox_h=int(h_ratio * FRAME_H),
        confidence=0.9,
    )


def _make_eyes(inter_px: float = 80, roi_w: int = 90) -> tuple:
    """
    Build left+right EyeRegionData such that the distance between
    eye-centre pixels equals inter_px.
    left_centre  = FRAME_W/2 - inter_px/2
    right_centre = FRAME_W/2 + inter_px/2
    roi_x = centre - roi_w/2
    """
    half = int(inter_px / 2)
    cx = FRAME_W // 2
    half_roi = roi_w // 2
    left = EyeRegionData(
        detected=True,
        roi_x=cx - half - half_roi,
        roi_y=200,
        roi_w=roi_w,
        roi_h=50,
    )
    right = EyeRegionData(
        detected=True,
        roi_x=cx + half - half_roi,
        roi_y=200,
        roi_w=roi_w,
        roi_h=50,
    )
    return left, right


class TestDistanceEstimatorClassify:
    def setup_method(self):
        self.est = DistanceEstimator(AppConfig())

    def _assess(self, face, left, right):
        return self.est.assess(face, left, right, FRAME_W, FRAME_H)

    def test_no_face_returns_unknown(self):
        result = self._assess(FaceData(detected=False), EyeRegionData(), EyeRegionData())
        assert result.status == STATUS_UNKNOWN

    def test_good_distance(self):
        face = _make_face(0.30)  # within good range (0.10 – 0.65)
        left, right = _make_eyes(inter_px=100)
        # Fill hysteresis buffer
        for _ in range(20):
            result = self._assess(face, left, right)
        assert result.status == STATUS_GOOD

    def test_too_close_wide_face(self):
        face = _make_face(0.75)  # > max_face_width_ratio (0.65) → too close
        left, right = _make_eyes(inter_px=200)
        for _ in range(20):
            result = self._assess(face, left, right)
        assert result.status == STATUS_TOO_CLOSE

    def test_too_far_small_face(self):
        face = _make_face(0.05)  # < min_face_width_ratio (0.10) → too far
        left, right = _make_eyes(inter_px=20)
        for _ in range(20):
            result = self._assess(face, left, right)
        assert result.status == STATUS_TOO_FAR

    def test_too_far_small_inter_eye(self):
        face = _make_face(0.20)  # face ratio OK but inter-eye too small
        left, right = _make_eyes(inter_px=20, roi_w=30)  # inter_px=20 < min(35)
        for _ in range(20):
            result = self._assess(face, left, right)
        assert result.status == STATUS_TOO_FAR

    def test_guidance_message_too_close(self):
        face = _make_face(0.75)
        left, right = _make_eyes(inter_px=200)
        for _ in range(20):
            result = self._assess(face, left, right)
        assert "far" in result.guidance_message.lower() or "farther" in result.guidance_message.lower()

    def test_guidance_message_too_far(self):
        face = _make_face(0.04)
        left, right = _make_eyes(inter_px=10, roi_w=20)
        for _ in range(20):
            result = self._assess(face, left, right)
        assert "closer" in result.guidance_message.lower()

    def test_score_is_in_range(self):
        face = _make_face(0.30)
        left, right = _make_eyes()
        for _ in range(20):
            result = self._assess(face, left, right)
        assert 0.0 <= result.score <= 1.0

    def test_inter_eye_distance_populated(self):
        face = _make_face(0.30)
        left, right = _make_eyes(inter_px=100)
        result = self._assess(face, left, right)
        # The centres should be ~100px apart (within a few px due to int rounding)
        assert abs(result.inter_eye_distance_px - 100) < 10

    def test_face_bbox_ratios_populated(self):
        face = _make_face(0.30, h_ratio=0.40)
        left, right = _make_eyes()
        result = self._assess(face, left, right)
        assert abs(result.face_bbox_width_ratio - 0.30) < 0.01
        assert abs(result.face_bbox_height_ratio - 0.40) < 0.01


class TestDistanceEstimatorHysteresis:
    def test_no_status_change_with_single_outlier(self):
        """
        Buffer is mostly GOOD but one frame is TOO_CLOSE —
        status should not flip because all frames must agree.
        """
        cfg = AppConfig()
        cfg.camera_distance.hysteresis_frames = 5
        est = DistanceEstimator(cfg)

        good_face = _make_face(0.30)
        close_face = _make_face(0.75)
        left, right = _make_eyes()

        # Fill buffer with GOOD
        for _ in range(10):
            result = est.assess(good_face, left, right, FRAME_W, FRAME_H)
        assert result.status == STATUS_GOOD

        # One TOO_CLOSE frame — should NOT change status
        result = est.assess(close_face, left, right, FRAME_W, FRAME_H)
        assert result.status == STATUS_GOOD  # hysteresis holds

    def test_status_changes_after_consistent_frames(self):
        """
        After hysteresis_frames consecutive TOO_CLOSE frames, status flips.
        """
        cfg = AppConfig()
        cfg.camera_distance.hysteresis_frames = 5
        est = DistanceEstimator(cfg)

        close_face = _make_face(0.75)
        left, right = _make_eyes(inter_px=200)

        for _ in range(10):
            result = est.assess(close_face, left, right, FRAME_W, FRAME_H)

        assert result.status == STATUS_TOO_CLOSE

    def test_reset_clears_buffer(self):
        cfg = AppConfig()
        cfg.camera_distance.hysteresis_frames = 3
        est = DistanceEstimator(cfg)

        close_face = _make_face(0.75)
        left, right = _make_eyes(inter_px=200)
        for _ in range(10):
            est.assess(close_face, left, right, FRAME_W, FRAME_H)

        est.reset()
        # After reset the buffer is empty; no face → UNKNOWN
        result = est.assess(FaceData(detected=False), EyeRegionData(), EyeRegionData(),
                            FRAME_W, FRAME_H)
        assert result.status == STATUS_UNKNOWN
