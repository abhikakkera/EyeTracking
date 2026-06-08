"""
Gaze smoothing filters — v0.2 fixes.

Kalman filter bugs fixed:
  1. np.linalg.inv(S) replaced with np.linalg.solve — numerically stable,
     doesn't crash when S is near-singular (low measurement noise edge case).
  2. Process noise Q now scales with dt² using the standard Singer model
     (constant velocity + white acceleration noise).
     v0.1 used a static Q = eye(4) × σ, which is wrong at variable frame rates.

Standard constant-velocity model:
  State:   x = [pos_x, pos_y, vel_x, vel_y]
  F(dt) =  [[1, 0, dt, 0 ],
             [0, 1, 0,  dt],
             [0, 0, 1,  0 ],
             [0, 0, 0,  1 ]]
  Q(dt) = σ_a² × [[dt⁴/4, 0,     dt³/2, 0    ],
                   [0,     dt⁴/4, 0,     dt³/2],
                   [dt³/2, 0,     dt²,   0    ],
                   [0,     dt³/2, 0,     dt²  ]]
  where σ_a² = process_noise (acceleration noise variance)
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
# Kalman filter — fixed
# ---------------------------------------------------------------------------

class KalmanGazeSmoother:
    """
    2-D Kalman filter with constant-velocity model.

    State vector: [x, y, vx, vy]
    Measurement:  [x, y]

    Numerically stable: uses np.linalg.solve instead of np.linalg.inv.
    Process noise Q scales properly with dt².
    """

    def __init__(self, process_noise: float, measurement_noise: float) -> None:
        self._sigma_a2 = max(process_noise, 1e-6)
        self._r_noise = max(measurement_noise, 1e-6)

        self.H = np.array([[1, 0, 0, 0],
                            [0, 1, 0, 0]], dtype=np.float64)
        self.R = np.eye(2, dtype=np.float64) * self._r_noise

        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 500.0   # high initial uncertainty
        self._initialised = False

    def _build_F(self, dt: float) -> np.ndarray:
        F = np.eye(4, dtype=np.float64)
        F[0, 2] = dt
        F[1, 3] = dt
        return F

    def _build_Q(self, dt: float) -> np.ndarray:
        """
        Standard discrete-time process noise for constant-velocity model.
        Derived from continuous white-noise acceleration (Singer model).
        """
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        q = self._sigma_a2
        Q = np.array([
            [dt4 / 4, 0,       dt3 / 2, 0      ],
            [0,       dt4 / 4, 0,       dt3 / 2],
            [dt3 / 2, 0,       dt2,     0      ],
            [0,       dt3 / 2, 0,       dt2    ],
        ], dtype=np.float64) * q
        return Q

    def update(self, measurement: Point2D, dt: float) -> Point2D:
        """Kalman update step. Returns smoothed (x, y) estimate."""
        z = np.array(measurement, dtype=np.float64)
        dt = max(dt, 1e-4)   # guard against zero dt

        if not self._initialised:
            self.x[:2] = z
            self._initialised = True
            return measurement

        F = self._build_F(dt)
        Q = self._build_Q(dt)

        # Prediction
        x_pred = F @ self.x
        P_pred = F @ self.P @ F.T + Q

        # Innovation
        y_innov = z - self.H @ x_pred
        S = self.H @ P_pred @ self.H.T + self.R

        # Kalman gain — use solve for numerical stability (avoids inv)
        # K = P_pred H^T S^{-1}  ⟺  K S^T = P_pred H^T  → solve for K^T
        K = np.linalg.solve(S.T, (P_pred @ self.H.T).T).T

        # Update
        self.x = x_pred + K @ y_innov
        self.P = (np.eye(4) - K @ self.H) @ P_pred

        return (float(self.x[0]), float(self.x[1]))

    def predict(self, dt: float) -> Point2D:
        """Return predicted position without incorporating a measurement."""
        if not self._initialised:
            return (0.5, 0.5)
        F = self._build_F(dt)
        x_pred = F @ self.x
        return (float(x_pred[0]), float(x_pred[1]))

    def reset(self) -> None:
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 500.0
        self._initialised = False


# ---------------------------------------------------------------------------
# Moving average
# ---------------------------------------------------------------------------

class MovingAverageSmoother:
    def __init__(self, window: int) -> None:
        self._buf: Deque[Point2D] = deque(maxlen=max(window, 1))

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
        self._alpha = max(0.01, min(1.0, alpha))
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
# Savitzky-Golay (causal — uses trailing window)
# ---------------------------------------------------------------------------

class SavitzkyGolaySmoother:
    def __init__(self, window: int, polyorder: int) -> None:
        self._window = window if window % 2 == 1 else window + 1
        self._polyorder = min(polyorder, self._window - 1)
        self._buf_x: Deque[float] = deque(maxlen=self._window)
        self._buf_y: Deque[float] = deque(maxlen=self._window)

    def update(self, measurement: Point2D, dt: float = 0.0) -> Point2D:  # noqa: ARG002
        self._buf_x.append(measurement[0])
        self._buf_y.append(measurement[1])
        if len(self._buf_x) < self._window:
            return measurement
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
    Facade: instantiate the configured smoother and expose a uniform update().

    Usage:
        smoother = GazeSmoother(config)
        sx, sy = smoother.update((raw_x, raw_y), dt_seconds)
    """

    def __init__(self, config: AppConfig) -> None:
        cfg = config.smoothing
        method = cfg.method.lower()

        if method == "kalman":
            self._impl = KalmanGazeSmoother(
                cfg.kalman_process_noise, cfg.kalman_measurement_noise
            )
        elif method == "exponential":
            self._impl = ExponentialSmoother(cfg.exponential_alpha)
        elif method == "savgol":
            self._impl = SavitzkyGolaySmoother(cfg.savgol_window, cfg.savgol_polyorder)
        elif method == "moving_average":
            self._impl = MovingAverageSmoother(cfg.moving_avg_window)
        else:
            logger.warning("Unknown smoothing method '%s', defaulting to Kalman", method)
            self._impl = KalmanGazeSmoother(
                cfg.kalman_process_noise, cfg.kalman_measurement_noise
            )
        logger.info("GazeSmoother: method=%s", method)

    def update(self, measurement: Point2D, dt: float = 0.033) -> Point2D:
        return self._impl.update(measurement, dt)

    def reset(self) -> None:
        self._impl.reset()
