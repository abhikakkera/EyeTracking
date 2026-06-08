"""
Gaze calibration module.

Calibration maps raw normalised pupil coordinates → screen pixel coordinates
using polynomial regression (degree 2).

Workflow:
    1.  Display calibration targets one by one.
    2.  For each target, collect N frames of pupil data while the subject
        fixates the target.
    3.  Average collected pupil positions → one calibration sample.
    4.  Fit a 2-D polynomial regression on the sample set.
    5.  During tracking, call map_to_screen() to convert raw gaze → screen.

Supports 5-point and 9-point calibration layouts.
The calibration profile is saved/loaded as JSON for reuse across sessions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

try:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import Ridge
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    Pipeline = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

Point2D = Tuple[float, float]

# Pre-defined calibration target layouts (normalised screen coords 0-1)
CALIBRATION_5PT: List[Point2D] = [
    (0.5, 0.5),   # centre
    (0.1, 0.1),   # top-left
    (0.9, 0.1),   # top-right
    (0.1, 0.9),   # bottom-left
    (0.9, 0.9),   # bottom-right
]

CALIBRATION_9PT: List[Point2D] = [
    (0.5, 0.5),
    (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
    (0.1, 0.5),             (0.9, 0.5),
    (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
]


class CalibrationProfile:
    """
    Holds a trained regression model mapping pupil → screen coordinates.
    """

    def __init__(self) -> None:
        self._model_x: Optional[object] = None
        self._model_y: Optional[object] = None
        self._fitted = False
        self._screen_size: Tuple[int, int] = (1920, 1080)
        self._num_points: int = 0

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(
        self,
        pupil_points: List[Point2D],
        screen_points: List[Point2D],
        screen_size: Tuple[int, int] = (1920, 1080),
        poly_degree: int = 2,
    ) -> None:
        """
        Fit the calibration model.

        Parameters
        ----------
        pupil_points  : list of (norm_x, norm_y) raw gaze positions
        screen_points : list of (screen_x, screen_y) target pixel positions
        screen_size   : (width, height) of the display in pixels
        poly_degree   : polynomial degree for the regression (2 is usually sufficient)
        """
        if len(pupil_points) != len(screen_points) or len(pupil_points) < 4:
            raise ValueError(
                f"Need at least 4 matched pupil/screen pairs, got {len(pupil_points)}"
            )

        if not _SKLEARN_AVAILABLE:
            raise RuntimeError(
                "scikit-learn is required for calibration. "
                "Install it with: pip install scikit-learn"
            )

        X = np.array(pupil_points, dtype=np.float64)
        y_x = np.array([p[0] for p in screen_points], dtype=np.float64)
        y_y = np.array([p[1] for p in screen_points], dtype=np.float64)

        def _make_pipeline(degree: int) -> "Pipeline":
            return Pipeline([
                ("poly", PolynomialFeatures(degree=degree, include_bias=True)),
                ("reg", Ridge(alpha=1.0)),
            ])

        self._model_x = _make_pipeline(poly_degree)
        self._model_y = _make_pipeline(poly_degree)
        self._model_x.fit(X, y_x)
        self._model_y.fit(X, y_y)

        self._fitted = True
        self._screen_size = screen_size
        self._num_points = len(pupil_points)

        logger.info(
            "Calibration fitted: %d points, degree=%d, screen=%dx%d",
            self._num_points, poly_degree, screen_size[0], screen_size[1],
        )

    def map_to_screen(self, gaze_norm: Point2D) -> Optional[Point2D]:
        """
        Map a normalised gaze position to screen pixel coordinates.

        Returns None if the model is not fitted.
        """
        if not self._fitted:
            return None
        X = np.array([[gaze_norm[0], gaze_norm[1]]])
        sx = float(self._model_x.predict(X)[0])
        sy = float(self._model_y.predict(X)[0])
        # Clamp to screen bounds
        sx = max(0.0, min(float(self._screen_size[0]), sx))
        sy = max(0.0, min(float(self._screen_size[1]), sy))
        return (sx, sy)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """
        Save the calibration data to a JSON file.
        Only the regression coefficients are serialised, not the sklearn objects,
        so this uses a simplified export.  Full sklearn model is not saved here
        to avoid pickle security issues.
        """
        if not self._fitted:
            raise RuntimeError("Cannot save: calibration is not fitted.")
        logger.warning(
            "Calibration persistence saves metadata only.  "
            "Refit from saved pupil/screen points to restore a full model."
        )
        meta = {
            "screen_size": list(self._screen_size),
            "num_points": self._num_points,
            "fitted": self._fitted,
        }
        with open(path, "w") as fh:
            json.dump(meta, fh, indent=2)

    def load(self, path: str | Path) -> None:
        """Load calibration metadata (for display only; model must be refit)."""
        with open(path) as fh:
            meta = json.load(fh)
        self._screen_size = tuple(meta.get("screen_size", [1920, 1080]))  # type: ignore[assignment]
        self._num_points = meta.get("num_points", 0)
        self._fitted = meta.get("fitted", False)


# ---------------------------------------------------------------------------
# Calibration data collector (used during the live calibration routine)
# ---------------------------------------------------------------------------

class CalibrationCollector:
    """
    Accumulates pupil measurements for each calibration target.

    Usage (see main.py --calibrate):
        collector = CalibrationCollector()
        collector.start_target(screen_pos, label="Point 1")
        for each_frame:
            collector.add_sample(gaze_norm)
        pupil_pos = collector.finish_target()
        # repeat for all targets…
        profile = collector.build_profile(screen_size)
    """

    def __init__(self, collect_frames: int = 30) -> None:
        self._collect_frames = collect_frames
        self._current_screen_pos: Optional[Point2D] = None
        self._current_samples: List[Point2D] = []
        self._pupil_points: List[Point2D] = []
        self._screen_points: List[Point2D] = []
        self._active = False

    def start_target(self, screen_pos: Point2D) -> None:
        self._current_screen_pos = screen_pos
        self._current_samples = []
        self._active = True

    def add_sample(self, gaze_norm: Point2D) -> bool:
        """
        Add a gaze sample.
        Returns True when enough samples have been collected.
        """
        if not self._active:
            return False
        self._current_samples.append(gaze_norm)
        return len(self._current_samples) >= self._collect_frames

    def finish_target(self) -> Optional[Point2D]:
        """
        Average the collected samples and store the calibration pair.
        Returns the averaged pupil position, or None on failure.
        """
        if not self._current_samples or self._current_screen_pos is None:
            return None
        xs = [p[0] for p in self._current_samples]
        ys = [p[1] for p in self._current_samples]
        avg = (float(np.mean(xs)), float(np.mean(ys)))
        self._pupil_points.append(avg)
        self._screen_points.append(self._current_screen_pos)
        self._active = False
        return avg

    def build_profile(
        self,
        screen_size: Tuple[int, int] = (1920, 1080),
    ) -> CalibrationProfile:
        """Fit and return a CalibrationProfile from all collected points."""
        profile = CalibrationProfile()
        profile.fit(self._pupil_points, self._screen_points, screen_size)
        return profile

    @property
    def collected_count(self) -> int:
        return len(self._pupil_points)

    @property
    def samples_this_target(self) -> int:
        return len(self._current_samples)
