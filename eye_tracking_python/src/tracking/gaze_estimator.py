"""
Gaze estimator.

Converts raw pupil/iris positions into normalised gaze coordinates:
    horizontal: 0.0 = far left of eye box, 0.5 = centre, 1.0 = far right
    vertical:   0.0 = top of eye box,      0.5 = centre, 1.0 = bottom

After calibration the estimator can also return approximate screen coordinates.

NOTE: This module estimates gaze direction from pupil position within the
visible eye region.  It is NOT a validated clinical gaze measurement system.
Accuracy depends on head pose, lighting, and calibration quality.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.data.schema import EyeRegionData, GazeData, IrisData, PupilData
from src.utils.geometry import normalize_point_in_box

logger = logging.getLogger(__name__)


class GazeEstimator:
    """
    Stateless gaze estimator.

    Usage:
        estimator = GazeEstimator()
        gaze = estimator.estimate(left_eye, right_eye, left_pupil, right_pupil)
    """

    def estimate(
        self,
        left_eye: EyeRegionData,
        right_eye: EyeRegionData,
        left_pupil: PupilData,
        right_pupil: PupilData,
        left_iris: Optional[IrisData] = None,
        right_iris: Optional[IrisData] = None,
    ) -> GazeData:
        """
        Compute normalised gaze from pupil positions within their eye boxes.

        If one eye's pupil is not detected, we use the other eye only.
        If neither pupil is detected, return centre (0.5, 0.5) with zero confidence.
        """
        left_norm = self._normalise_pupil(left_pupil, left_eye, left_iris)
        right_norm = self._normalise_pupil(right_pupil, right_eye, right_iris)

        left_valid = left_pupil.detected and left_eye.detected
        right_valid = right_pupil.detected and right_eye.detected

        if left_valid and right_valid:
            avg_x = (left_norm[0] + right_norm[0]) / 2.0
            avg_y = (left_norm[1] + right_norm[1]) / 2.0
            confidence = (left_pupil.confidence + right_pupil.confidence) / 2.0
        elif left_valid:
            avg_x, avg_y = left_norm
            confidence = left_pupil.confidence * 0.7
        elif right_valid:
            avg_x, avg_y = right_norm
            confidence = right_pupil.confidence * 0.7
        else:
            avg_x, avg_y = 0.5, 0.5
            confidence = 0.0

        # Gaze direction vector (dx, dy) where 0 = centre
        gaze_dx = avg_x - 0.5
        gaze_dy = avg_y - 0.5

        return GazeData(
            left_normalized=left_norm,
            right_normalized=right_norm,
            average_normalized=(avg_x, avg_y),
            gaze_vector=(gaze_dx, gaze_dy),
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _normalise_pupil(
        self,
        pupil: PupilData,
        eye: EyeRegionData,
        iris: Optional[IrisData],
    ) -> tuple[float, float]:
        """
        Compute the normalised position of the pupil centre within the eye box.

        If MediaPipe iris data is available AND the pupil was not detected,
        fall back to the iris centre as an approximation.
        """
        if not eye.detected:
            return (0.5, 0.5)

        # Choose the best available centre
        if pupil.detected:
            px, py = pupil.center_frame
        elif iris is not None and iris.detected:
            px, py = iris.center_frame
        else:
            return (0.5, 0.5)

        return normalize_point_in_box(
            (px, py),
            float(eye.roi_x),
            float(eye.roi_y),
            float(eye.roi_w),
            float(eye.roi_h),
        )
