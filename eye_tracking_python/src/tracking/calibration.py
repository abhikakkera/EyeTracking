"""
Calibration module — v0.2 (fixes broken save/load).

v0.1 critical bug: save() explicitly stated it only saved metadata,
not the actual sklearn model.  load() set self._fitted = True while
self._model_x remained None, causing crashes on map_to_screen().

v0.2 fix: use joblib.dump/load to persist the full sklearn Pipeline objects.
Also adds:
  - per-point error measurement
  - mean_error_px and max_error_px
  - user-facing quality warning when error is high
  - outlier rejection during sample collection (IQR filter)
"""
from __future__ import annotations

import json
import logging
import uuid
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

try:
    from joblib import dump as joblib_dump, load as joblib_load
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

logger = logging.getLogger(__name__)
Point2D = Tuple[float, float]

# Calibration warning threshold: if mean error > this, warn the user.
_ACCEPTABLE_ERROR_PX = 40.0

CALIBRATION_5PT: List[Point2D] = [
    (0.5, 0.5),
    (0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9),
]

CALIBRATION_9PT: List[Point2D] = [
    (0.5, 0.5),
    (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
    (0.1, 0.5),             (0.9, 0.5),
    (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
]


class CalibrationProfile:
    """
    Trained regression model mapping normalised pupil coords → screen pixels.

    Save/load with joblib so the model survives process restarts.
    """

    def __init__(self) -> None:
        self._model_x: Optional[object] = None
        self._model_y: Optional[object] = None
        self._fitted = False
        self._screen_size: Tuple[int, int] = (1920, 1080)
        self._num_points: int = 0
        self._mean_error_px: float = 0.0
        self._max_error_px: float = 0.0
        self._per_point_errors: List[float] = []
        self._pupil_points: List[Point2D] = []
        self._screen_points: List[Point2D] = []
        self.calibration_id: str = str(uuid.uuid4())[:8]

    @property
    def is_fitted(self) -> bool:
        return self._fitted and self._model_x is not None

    @property
    def mean_error_px(self) -> float:
        return self._mean_error_px

    @property
    def is_acceptable(self) -> bool:
        return self._fitted and self._mean_error_px <= _ACCEPTABLE_ERROR_PX

    def fit(
        self,
        pupil_points: List[Point2D],
        screen_points: List[Point2D],
        screen_size: Tuple[int, int] = (1920, 1080),
        poly_degree: int = 2,
    ) -> None:
        if len(pupil_points) != len(screen_points) or len(pupil_points) < 4:
            raise ValueError(
                f"Need ≥4 matched pairs, got {len(pupil_points)}"
            )
        if not _SKLEARN_AVAILABLE:
            raise RuntimeError("scikit-learn required: pip install scikit-learn")

        X = np.array(pupil_points, dtype=np.float64)
        y_x = np.array([p[0] for p in screen_points], dtype=np.float64)
        y_y = np.array([p[1] for p in screen_points], dtype=np.float64)

        def _pipeline(degree: int) -> Pipeline:
            return Pipeline([
                ("poly", PolynomialFeatures(degree=degree, include_bias=True)),
                ("reg", Ridge(alpha=1.0)),
            ])

        self._model_x = _pipeline(poly_degree)
        self._model_y = _pipeline(poly_degree)
        self._model_x.fit(X, y_x)
        self._model_y.fit(X, y_y)

        # Measure per-point error
        pred_x = self._model_x.predict(X)
        pred_y = self._model_y.predict(X)
        errors = [
            float(np.hypot(px - sx, py - sy))
            for (px, py, sx, sy) in zip(pred_x, pred_y, y_x, y_y)
        ]
        self._per_point_errors = errors
        self._mean_error_px = float(np.mean(errors))
        self._max_error_px = float(np.max(errors))

        self._fitted = True
        self._screen_size = screen_size
        self._num_points = len(pupil_points)
        self._pupil_points = list(pupil_points)
        self._screen_points = list(screen_points)

        logger.info(
            "Calibration fitted: %d pts  mean_err=%.1fpx  max_err=%.1fpx",
            self._num_points, self._mean_error_px, self._max_error_px,
        )
        if not self.is_acceptable:
            logger.warning(
                "Calibration mean error %.1fpx exceeds acceptable limit %.1fpx. "
                "Consider repeating calibration with the subject holding still.",
                self._mean_error_px, _ACCEPTABLE_ERROR_PX,
            )

    def map_to_screen(self, gaze_norm: Point2D) -> Optional[Point2D]:
        if not self.is_fitted:
            return None
        X = np.array([[gaze_norm[0], gaze_norm[1]]])
        sx = float(self._model_x.predict(X)[0])
        sy = float(self._model_y.predict(X)[0])
        sx = max(0.0, min(float(self._screen_size[0]), sx))
        sy = max(0.0, min(float(self._screen_size[1]), sy))
        return (sx, sy)

    # ------------------------------------------------------------------
    # Persistence — FIXED in v0.2
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """
        Save the full calibration model to disk using joblib.
        Falls back to JSON metadata-only if joblib is unavailable.
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot save: calibration is not fitted.")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if _JOBLIB_AVAILABLE:
            data = {
                "calibration_id": self.calibration_id,
                "screen_size": self._screen_size,
                "num_points": self._num_points,
                "mean_error_px": self._mean_error_px,
                "max_error_px": self._max_error_px,
                "per_point_errors": self._per_point_errors,
                "pupil_points": self._pupil_points,
                "screen_points": self._screen_points,
                "model_x": self._model_x,
                "model_y": self._model_y,
            }
            # Save as .joblib; keep a sidecar JSON for human inspection
            joblib_path = path.with_suffix(".joblib")
            joblib_dump(data, joblib_path)
            meta = {
                "joblib_file": str(joblib_path),
                "calibration_id": self.calibration_id,
                "num_points": self._num_points,
                "mean_error_px": round(self._mean_error_px, 2),
                "max_error_px": round(self._max_error_px, 2),
                "acceptable": self.is_acceptable,
                "screen_size": list(self._screen_size),
            }
            with open(path, "w") as fh:
                json.dump(meta, fh, indent=2)
            logger.info("Calibration saved: %s (joblib: %s)", path, joblib_path)
        else:
            # joblib not available — save metadata only with a clear warning
            logger.error(
                "joblib not available: pip install joblib. "
                "Saving metadata only — model will not be reloadable."
            )
            meta = {
                "warning": "Model not saved — install joblib",
                "num_points": self._num_points,
                "mean_error_px": round(self._mean_error_px, 2),
                "screen_size": list(self._screen_size),
                "fitted": False,  # mark as not usable
            }
            with open(path, "w") as fh:
                json.dump(meta, fh, indent=2)

    def load(self, path: str | Path) -> None:
        """
        Load a calibration model from disk.
        Reads the joblib file referenced in the JSON sidecar.
        """
        path = Path(path)
        with open(path) as fh:
            meta = json.load(fh)

        if not _JOBLIB_AVAILABLE:
            raise RuntimeError("joblib required to load calibration: pip install joblib")

        joblib_path = Path(meta.get("joblib_file", path.with_suffix(".joblib")))
        if not joblib_path.exists():
            raise FileNotFoundError(f"Calibration joblib file not found: {joblib_path}")

        data = joblib_load(joblib_path)
        self._model_x = data["model_x"]
        self._model_y = data["model_y"]
        self._screen_size = tuple(data["screen_size"])
        self._num_points = data["num_points"]
        self._mean_error_px = data.get("mean_error_px", 0.0)
        self._max_error_px = data.get("max_error_px", 0.0)
        self._per_point_errors = data.get("per_point_errors", [])
        self._pupil_points = data.get("pupil_points", [])
        self._screen_points = data.get("screen_points", [])
        self.calibration_id = data.get("calibration_id", "loaded")
        self._fitted = self._model_x is not None

        logger.info(
            "Calibration loaded: id=%s  pts=%d  mean_err=%.1fpx",
            self.calibration_id, self._num_points, self._mean_error_px,
        )


# ---------------------------------------------------------------------------
# Sample collector
# ---------------------------------------------------------------------------

class CalibrationCollector:
    """
    Accumulates fixation samples per calibration target, with IQR outlier rejection.
    """

    def __init__(self, collect_frames: int = 40) -> None:
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
        if not self._active:
            return False
        self._current_samples.append(gaze_norm)
        return len(self._current_samples) >= self._collect_frames

    def finish_target(self) -> Optional[Point2D]:
        """
        Average samples after IQR-based outlier rejection.
        Returns the averaged pupil position for this target.
        """
        if not self._current_samples or self._current_screen_pos is None:
            return None

        xs = np.array([p[0] for p in self._current_samples])
        ys = np.array([p[1] for p in self._current_samples])

        # Remove outliers beyond 1.5 × IQR in each dimension
        def _iqr_mask(arr: np.ndarray) -> np.ndarray:
            q1, q3 = np.percentile(arr, [25, 75])
            iqr = q3 - q1
            return (arr >= q1 - 1.5 * iqr) & (arr <= q3 + 1.5 * iqr)

        mask = _iqr_mask(xs) & _iqr_mask(ys)
        if mask.sum() < 3:
            mask = np.ones(len(xs), dtype=bool)   # fall back to all samples

        avg = (float(np.mean(xs[mask])), float(np.mean(ys[mask])))
        self._pupil_points.append(avg)
        self._screen_points.append(self._current_screen_pos)
        self._active = False
        logger.debug(
            "Calibration target: screen=%s  pupil=%s  samples=%d (used %d after IQR filter)",
            self._current_screen_pos, avg, len(self._current_samples), int(mask.sum()),
        )
        return avg

    def build_profile(
        self,
        screen_size: Tuple[int, int] = (1920, 1080),
    ) -> CalibrationProfile:
        profile = CalibrationProfile()
        profile.fit(self._pupil_points, self._screen_points, screen_size)
        return profile

    @property
    def collected_count(self) -> int:
        return len(self._pupil_points)

    @property
    def samples_this_target(self) -> int:
        return len(self._current_samples)
