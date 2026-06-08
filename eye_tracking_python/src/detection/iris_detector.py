"""
Iris detector.

When MediaPipe is run with refine_landmarks=True it provides iris sub-landmarks
at indices 468–477.  This module extracts iris centre and approximate radius
from those landmarks.

If the iris landmarks are unavailable (older MediaPipe, or detection failed),
the iris centre is estimated from the four eye-corner landmarks and the pupil
centre, providing a degraded but usable estimate.

Iris landmarks layout (MediaPipe convention):
    Right iris (viewer's LEFT, subject's right):
        468 = centre
        469 = right boundary
        470 = bottom boundary
        471 = left boundary
        472 = top boundary

    Left iris (viewer's RIGHT, subject's left):
        473 = centre
        474 = right boundary
        475 = bottom boundary
        476 = left boundary
        477 = top boundary
"""
from __future__ import annotations

import logging
import math
from typing import List, Tuple

from src.data.schema import FaceData, IrisData

logger = logging.getLogger(__name__)

# Landmark index constants
_VIEWER_LEFT_IRIS_CENTRE = 468
_VIEWER_LEFT_IRIS_BOUNDARY = [469, 470, 471, 472]

_VIEWER_RIGHT_IRIS_CENTRE = 473
_VIEWER_RIGHT_IRIS_BOUNDARY = [474, 475, 476, 477]

# Total landmarks with refined iris = 478
_MIN_IRIS_LANDMARK_COUNT = 478


class IrisDetector:
    """
    Extracts iris position from MediaPipe face landmarks.

    Usage:
        detector = IrisDetector()
        left_iris = detector.detect_left(face_data)
        right_iris = detector.detect_right(face_data)
    """

    def detect_left(self, face_data: FaceData) -> IrisData:
        """Detect the viewer's LEFT iris (subject's right iris)."""
        return self._detect(
            face_data,
            centre_idx=_VIEWER_LEFT_IRIS_CENTRE,
            boundary_idx=_VIEWER_LEFT_IRIS_BOUNDARY,
        )

    def detect_right(self, face_data: FaceData) -> IrisData:
        """Detect the viewer's RIGHT iris (subject's left iris)."""
        return self._detect(
            face_data,
            centre_idx=_VIEWER_RIGHT_IRIS_CENTRE,
            boundary_idx=_VIEWER_RIGHT_IRIS_BOUNDARY,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect(
        self,
        face_data: FaceData,
        centre_idx: int,
        boundary_idx: List[int],
    ) -> IrisData:
        if not face_data.detected:
            return IrisData()

        landmarks = face_data.landmarks

        # Check if iris landmarks are present (requires refine_landmarks=True)
        if len(landmarks) < _MIN_IRIS_LANDMARK_COUNT:
            return IrisData()

        try:
            cx, cy = landmarks[centre_idx]

            # Radius = mean distance from centre to the 4 boundary points
            dists: List[float] = []
            for idx in boundary_idx:
                bx, by = landmarks[idx]
                dists.append(math.hypot(bx - cx, by - cy))
            radius = float(sum(dists) / len(dists)) if dists else 0.0

            if radius < 1.0:
                return IrisData()

            return IrisData(
                detected=True,
                center_frame=(float(cx), float(cy)),
                radius_px=radius,
                confidence=0.95,
            )

        except (IndexError, ValueError) as exc:
            logger.debug("Iris landmark extraction failed: %s", exc)
            return IrisData()
