"""
Unit tests for src/utils/geometry.py
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.utils.geometry import (
    clamp,
    compute_angle_deg,
    compute_velocity,
    contour_circularity,
    dispersion,
    euclidean_distance,
    eye_aspect_ratio,
    midpoint,
    normalize_point_in_box,
)


class TestEuclideanDistance:
    def test_zero(self):
        assert euclidean_distance((0, 0), (0, 0)) == 0.0

    def test_horizontal(self):
        assert euclidean_distance((0, 0), (3, 0)) == pytest.approx(3.0)

    def test_diagonal(self):
        assert euclidean_distance((0, 0), (3, 4)) == pytest.approx(5.0)

    def test_negative_coords(self):
        assert euclidean_distance((-1, -1), (2, 3)) == pytest.approx(5.0)


class TestMidpoint:
    def test_basic(self):
        mp = midpoint((0, 0), (4, 4))
        assert mp == pytest.approx((2.0, 2.0))

    def test_same_point(self):
        mp = midpoint((3, 5), (3, 5))
        assert mp == pytest.approx((3.0, 5.0))


class TestContourCircularity:
    def test_perfect_circle(self):
        r = 10.0
        area = math.pi * r ** 2
        perimeter = 2 * math.pi * r
        c = contour_circularity(area, perimeter)
        assert c == pytest.approx(1.0, rel=1e-4)

    def test_zero_perimeter(self):
        assert contour_circularity(10.0, 0.0) == 0.0

    def test_square_is_less_than_one(self):
        # Square: area=1, perimeter=4 → circularity = 4π/16 ≈ 0.785
        c = contour_circularity(1.0, 4.0)
        assert c < 1.0
        assert c > 0.0


class TestEyeAspectRatio:
    def test_open_eye(self):
        # Wide open eye: tall vertical distances, normal horizontal
        landmarks = [
            (0.0, 0.0),   # P1 left corner
            (1.0, -3.0),  # P2 upper-left
            (2.0, -3.0),  # P3 upper-right
            (3.0, 0.0),   # P4 right corner
            (2.0, 3.0),   # P5 lower-right
            (1.0, 3.0),   # P6 lower-left
        ]
        ear = eye_aspect_ratio(landmarks)
        assert ear > 0.25

    def test_closed_eye(self):
        # Eye almost closed: vertical distances ≈ 0
        landmarks = [
            (0.0, 0.0),
            (1.0, -0.1),
            (2.0, -0.1),
            (3.0, 0.0),
            (2.0, 0.1),
            (1.0, 0.1),
        ]
        ear = eye_aspect_ratio(landmarks)
        assert ear < 0.1

    def test_wrong_landmark_count(self):
        with pytest.raises(ValueError):
            eye_aspect_ratio([(0, 0)] * 5)

    def test_zero_horizontal_distance(self):
        landmarks = [(0, 0)] * 6
        assert eye_aspect_ratio(landmarks) == 0.0


class TestNormalizePointInBox:
    def test_top_left(self):
        p = normalize_point_in_box((10.0, 20.0), 10.0, 20.0, 100.0, 50.0)
        assert p == pytest.approx((0.0, 0.0))

    def test_bottom_right(self):
        p = normalize_point_in_box((110.0, 70.0), 10.0, 20.0, 100.0, 50.0)
        assert p == pytest.approx((1.0, 1.0))

    def test_centre(self):
        p = normalize_point_in_box((60.0, 45.0), 10.0, 20.0, 100.0, 50.0)
        assert p == pytest.approx((0.5, 0.5))

    def test_zero_width_returns_centre(self):
        p = normalize_point_in_box((5.0, 5.0), 0.0, 0.0, 0.0, 0.0)
        assert p == (0.5, 0.5)

    def test_clamp_outside(self):
        p = normalize_point_in_box((200.0, 200.0), 10.0, 20.0, 100.0, 50.0)
        assert 0.0 <= p[0] <= 1.0
        assert 0.0 <= p[1] <= 1.0


class TestComputeVelocity:
    def test_stationary(self):
        vx, vy, speed = compute_velocity((5.0, 5.0), (5.0, 5.0), 0.033)
        assert speed == pytest.approx(0.0)

    def test_horizontal_movement(self):
        _, _, speed = compute_velocity((0.0, 0.0), (10.0, 0.0), 1.0)
        assert speed == pytest.approx(10.0)

    def test_zero_dt(self):
        vx, vy, speed = compute_velocity((0.0, 0.0), (10.0, 0.0), 0.0)
        assert speed == 0.0


class TestComputeAngle:
    def test_rightward(self):
        a = compute_angle_deg(1.0, 0.0)
        assert a == pytest.approx(0.0)

    def test_upward_screen(self):
        # dy is negative in screen coords for upward motion
        a = compute_angle_deg(0.0, -1.0)
        assert a == pytest.approx(90.0)

    def test_leftward(self):
        a = compute_angle_deg(-1.0, 0.0)
        assert a == pytest.approx(180.0)


class TestClamp:
    def test_within(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_below(self):
        assert clamp(-1.0, 0.0, 1.0) == 0.0

    def test_above(self):
        assert clamp(2.0, 0.0, 1.0) == 1.0


class TestDispersion:
    def test_single_point(self):
        assert dispersion([(0.5, 0.5)]) == 0.0

    def test_spread(self):
        points = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
        d = dispersion(points)
        # (max_x - min_x) + (max_y - min_y) = 1 + 1 = 2
        assert d == pytest.approx(2.0)

    def test_empty(self):
        assert dispersion([]) == 0.0
