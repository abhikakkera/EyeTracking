"""
Unit tests for src/tracking/smoothing.py
"""
from __future__ import annotations

import pytest

from config import AppConfig, SmoothingConfig
from src.tracking.smoothing import (
    ExponentialSmoother,
    GazeSmoother,
    KalmanGazeSmoother,
    MovingAverageSmoother,
)


def _make_config(method: str) -> AppConfig:
    cfg = AppConfig()
    cfg.smoothing = SmoothingConfig(method=method)
    return cfg


class TestKalmanSmoother:
    def test_first_measurement_returned_unchanged(self):
        ks = KalmanGazeSmoother(process_noise=0.01, measurement_noise=0.1)
        result = ks.update((0.5, 0.5), dt=0.033)
        assert result == pytest.approx((0.5, 0.5), abs=0.01)

    def test_smooths_step_input(self):
        """After a sudden jump, the Kalman output should approach (not equal) new position."""
        ks = KalmanGazeSmoother(process_noise=0.01, measurement_noise=0.1)
        # Warm up at (0.5, 0.5)
        for _ in range(10):
            ks.update((0.5, 0.5), dt=0.033)
        # Jump to (1.0, 1.0)
        out = ks.update((1.0, 1.0), dt=0.033)
        # Output should move toward 1.0 but not jump there instantly
        assert out[0] < 1.0 and out[0] > 0.5

    def test_reset_clears_state(self):
        ks = KalmanGazeSmoother(0.01, 0.1)
        for _ in range(5):
            ks.update((0.8, 0.8), dt=0.033)
        ks.reset()
        # After reset, first measurement should be returned directly
        out = ks.update((0.2, 0.2), dt=0.033)
        assert out == pytest.approx((0.2, 0.2), abs=0.01)

    def test_output_bounded_near_input_after_convergence(self):
        ks = KalmanGazeSmoother(0.01, 0.1)
        # Feed many frames of a stable position
        pos = (0.3, 0.7)
        for _ in range(50):
            out = ks.update(pos, dt=0.033)
        # Output should be close to input after convergence
        assert out == pytest.approx(pos, abs=0.05)

    def test_handles_zero_dt(self):
        ks = KalmanGazeSmoother(0.01, 0.1)
        ks.update((0.5, 0.5), 0.033)
        # Should not raise with dt=0 (uninitialised path returns measurement)
        out = ks.update((0.5, 0.5), 0.0)
        assert len(out) == 2


class TestMovingAverageSmoother:
    def test_single_sample(self):
        ma = MovingAverageSmoother(window=5)
        out = ma.update((0.3, 0.7))
        assert out == pytest.approx((0.3, 0.7))

    def test_averages_correctly(self):
        ma = MovingAverageSmoother(window=3)
        ma.update((0.0, 0.0))
        ma.update((1.0, 1.0))
        out = ma.update((0.5, 0.5))
        assert out == pytest.approx((0.5, 0.5))

    def test_window_sliding(self):
        ma = MovingAverageSmoother(window=2)
        ma.update((0.0, 0.0))
        ma.update((1.0, 1.0))
        out = ma.update((1.0, 1.0))
        # Window is now [(1.0,1.0),(1.0,1.0)]
        assert out == pytest.approx((1.0, 1.0))

    def test_reset_clears(self):
        ma = MovingAverageSmoother(window=5)
        for _ in range(4):
            ma.update((0.9, 0.9))
        ma.reset()
        out = ma.update((0.1, 0.1))
        assert out == pytest.approx((0.1, 0.1))


class TestExponentialSmoother:
    def test_first_sample_unchanged(self):
        es = ExponentialSmoother(alpha=0.3)
        out = es.update((0.4, 0.6))
        assert out == pytest.approx((0.4, 0.6))

    def test_smooths_toward_new_value(self):
        es = ExponentialSmoother(alpha=0.5)
        es.update((0.0, 0.0))
        out = es.update((1.0, 1.0))
        # Expected: 0.5*1.0 + 0.5*0.0 = 0.5
        assert out == pytest.approx((0.5, 0.5))

    def test_alpha_one_passes_through(self):
        es = ExponentialSmoother(alpha=1.0)
        es.update((0.0, 0.0))
        out = es.update((0.8, 0.2))
        assert out == pytest.approx((0.8, 0.2))

    def test_reset(self):
        es = ExponentialSmoother(alpha=0.3)
        es.update((0.9, 0.9))
        es.reset()
        out = es.update((0.1, 0.1))
        assert out == pytest.approx((0.1, 0.1))


class TestGazeSmoother:
    @pytest.mark.parametrize("method", ["kalman", "exponential", "moving_average", "savgol"])
    def test_factory_creates_without_error(self, method: str):
        cfg = _make_config(method)
        gs = GazeSmoother(cfg)
        out = gs.update((0.5, 0.5), dt=0.033)
        assert len(out) == 2

    def test_unknown_method_falls_back(self):
        cfg = _make_config("nonexistent_method")
        gs = GazeSmoother(cfg)  # should not raise
        out = gs.update((0.5, 0.5), dt=0.033)
        assert len(out) == 2

    def test_output_in_valid_range(self):
        """Smoother output for inputs in [0,1] should stay near [0,1]."""
        cfg = _make_config("kalman")
        gs = GazeSmoother(cfg)
        for x in [0.0, 0.25, 0.5, 0.75, 1.0]:
            out = gs.update((x, 1 - x), dt=0.033)
            # Allow some tolerance for Kalman lag, but extreme values indicate a bug
            assert -0.5 <= out[0] <= 1.5
            assert -0.5 <= out[1] <= 1.5
