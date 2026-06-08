"""
Gaze position smoothing filters.

Four implementations are available; choose via SmoothingConfig.method:
    "moving_average"  — simple N-frame mean (no lag compensation)
    "exponential"     — exponential moving average (configurable lag vs smoothness)
    "savgol"          — Savitzky-Golay (good lag characteristics, requires buffer)
    "kalman"          — 2-D Kalman filter with constant-velocity model (default)

Raw positions are NEVER overwritten.  The caller stores both raw and smoothed
series independently (see FrameRecord.smooth_gaze_x / smooth_gaze_y).
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Optional, Tuple

import numpy as np
from scipy.signal import savgol_filter

from config import AppConfig

logger = logging.getLogger(__name__)

Point2D = Tuple[float, float]


# ---------------------------------------------------------------------------
# Kalman filter (constant-velocity 2-D model)
# ---------------------------------------------------------------------------

class KalmanGazeSmoother:
    """
    2-D Kalman filter tracking gaze position and velocity.

    State vector:  [x, y, vx, vy]
    Measurement:   [x, y]
    Motion model:  constant velocity with Gaussian process noise

    The filter smooths the observed gaze position while maintaining a
    physics-based prediction that tolerates brief occlusions.
    """

    def __init__(self, process_noise: float, measurement_noise: float) -> None:
        self._Q_scale = process_noise
        self._R_scale = measurement_noise

        # State transition:  x_{t+1} = F · x_t  (dt inserted per update)
        self.F = np.eye(4, dtype=np.float64)

        # Measurement model:  z = H · x
        self.H = np.array([[1, 0, 0, 0],
                            [0, 1, 0, 0]], dtype=np.float64)

        # Covariances (scaled identities; updated once per step)
        self.Q = np.eye(4, dtype=np.float64) * process_noise
        self.R = np.eye(2, dtype=np.float64) * measurement_noise

        # State and error covariance
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 1.0
        self._initialised = False

    def update(self, measurement: Point2D, dt: float) -> Point2D:
        """
        Incorporate a new measurement and return the smoothed estimate.

        Parameters
        ----------
        measurement : (x, y) raw gaze position
        dt : elapsed time since the last call, in seconds
        """
        z = np.array(measurement, dtype=np.float64)

        if not self._initialised:
            self.x = np.array([z[0], z[1], 0.0, 0.0])
            self._initialised = True
            return measurement

        # --- Prediction step -------------------------------------------------
        # Update state transition matrix with actual dt
        self.F[0, 2] = dt
        self.F[1, 3] = dt

        x_pred = self.F @ self.x
        P_pred = self.F @ self.P @ self.F.T + self.Q

        # --- Update step -----------------------------------------------------
        y_innov = z - self.H @ x_pred                     # innovation
        S = self.H @ P_pred @ self.H.T + self.R           # innovation covariance
        K = P_pred @ self.H.T @ np.linalg.inv(S)          # Kalman gain

        self.x = x_pred + K @ y_innov
        self.P = (np.eye(4) - K @ self.H) @ P_pred

        return (float(self.x[0]), float(self.x[1]))

    def reset(self) -> None:
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64)
        self._initialised = False


# ---------------------------------------------------------------------------
# Moving average
# ---------------------------------------------------------------------------

class MovingAverageSmoother:
    def __init__(self, window: int) -> None:
        self._buf: Deque[Point2D] = deque(maxlen=window)

    def update(self, measurement: Point2D, dt: float = 0.0) -> Point2D:  # noqa: ARG002
        self._buf.append(measurement)
        xs = [p[0] for p in self._buf]
        ys = [p[1] for p in self._buf]
        return (float(np.mean(xs)), float(np.mean(ys)))

    def reset(self) -> None:
        self._buf.clear()


# ---------------------------------------------------------------------------
# Exponential moving average
# ---------------------------------------------------------------------------

class ExponentialSmoother:
    def __init__(self, alpha: float) -> None:
        """alpha ∈ (0,1]: higher = less smoothing, lower = more lag."""
        self._alpha = alpha
        self._prev: Optional[Point2D] = None

    def update(self, measurement: Point2D, dt: float = 0.0) -> Point2D:  # noqa: ARG002
        if self._prev is None:
            self._prev = measurement
            return measurement
        sx = self._alpha * measurement[0] + (1 - self._alpha) * self._prev[0]
        sy = self._alpha * measurement[1] + (1 - self._alpha) * self._prev[1]
        self._prev = (sx, sy)
        return self._prev

    def reset(self) -> None:
        self._prev = None


# ---------------------------------------------------------------------------
# Savitzky-Golay (batch-causal: uses trailing window only)
# ---------------------------------------------------------------------------

class SavitzkyGolaySmoother:
    def __init__(self, window: int, polyorder: int) -> None:
        self._window = window if window % 2 == 1 else window + 1
        self._polyorder = polyorder
        self._buf_x: Deque[float] = deque(maxlen=self._window)
        self._buf_y: Deque[float] = deque(maxlen=self._window)

    def update(self, measurement: Point2D, dt: float = 0.0) -> Point2D:  # noqa: ARG002
        self._buf_x.append(measurement[0])
        self._buf_y.append(measurement[1])
        if len(self._buf_x) < self._window:
            return measurement  # not enough data yet; return raw
        sx = float(savgol_filter(list(self._buf_x), self._window, self._polyorder)[-1])
        sy = float(savgol_filter(list(self._buf_y), self._window, self._polyorder)[-1])
        return (sx, sy)

    def reset(self) -> None:
        self._buf_x.clear()
        self._buf_y.clear()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class GazeSmoother:
    """
    Facade that instantiates the configured smoother and exposes a uniform
    update() interface.

    Usage:
        smoother = GazeSmoother(config)
        smooth_x, smooth_y = smoother.update((raw_x, raw_y), dt)
    """

    def __init__(self, config: AppConfig) -> None:
        cfg = config.smoothing
        method = cfg.method.lower()

        if method == "kalman":
            self._impl = KalmanGazeSmoother(cfg.kalman_process_noise, cfg.kalman_measurement_noise)
        elif method == "exponential":
            self._impl = ExponentialSmoother(cfg.exponential_alpha)
        elif method == "savgol":
            self._impl = SavitzkyGolaySmoother(cfg.savgol_window, cfg.savgol_polyorder)
        elif method == "moving_average":
            self._impl = MovingAverageSmoother(cfg.moving_avg_window)
        else:
            logger.warning("Unknown smoothing method '%s', defaulting to Kalman", method)
            self._impl = KalmanGazeSmoother(cfg.kalman_process_noise, cfg.kalman_measurement_noise)

        logger.info("GazeSmoother: method=%s", method)

    def update(self, measurement: Point2D, dt: float = 0.033) -> Point2D:
        return self._impl.update(measurement, dt)

    def reset(self) -> None:
        self._impl.reset()
