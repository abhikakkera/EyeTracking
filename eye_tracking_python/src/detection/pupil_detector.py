"""
Pupil detector with a four-level fallback hierarchy.

Detection priority (highest to lowest confidence):
    1. Contour-based ellipse fit  — best accuracy in good lighting
    2. Hough circle transform     — works when contours are fragmented
    3. Darkest-region centroid    — last geometric resort
    4. Temporal prediction        — uses the previous frame's result

The eye ROI is pre-processed with CLAHE and Gaussian blur to increase
robustness to lighting variation and motion blur.

All coordinates returned are in two spaces:
    center_roi   — within the (normalised) eye ROI image
    center_frame — within the original full-resolution frame
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from config import AppConfig
from src.data.schema import DetectionMethod, EyeRegionData, PupilData
from src.utils.geometry import contour_circularity

logger = logging.getLogger(__name__)


class PupilDetector:
    """
    Stateful pupil detector that keeps one frame of history for temporal
    prediction fallback.

    Usage:
        detector = PupilDetector(config)
        pupil = detector.detect(eye_region)   # call per-eye, per-frame
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.detection
        self._last_result: Optional[PupilData] = None

        # Pre-build CLAHE object (creating per-frame is wasteful)
        self._clahe = cv2.createCLAHE(
            clipLimit=self._cfg.pupil_clahe_clip_limit,
            tileGridSize=self._cfg.pupil_clahe_grid_size,
        )

    def detect(self, eye_region: EyeRegionData) -> PupilData:
        """
        Detect the pupil in a single eye ROI.

        Returns an empty PupilData() with detected=False when every method
        fails; never raises.
        """
        if not eye_region.detected or eye_region.roi_image is None:
            return PupilData()

        try:
            gray = self._preprocess(eye_region.roi_image)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pupil pre-processing failed: %s", exc)
            return PupilData()

        roi_w = eye_region.roi_image.shape[1]
        roi_h = eye_region.roi_image.shape[0]

        # --- Method 1: contour + ellipse fit ---------------------------------
        result = self._detect_contour(gray, eye_region, roi_w, roi_h)
        if result.confidence >= 0.5:
            self._last_result = result
            return result

        # --- Method 2: Hough circle transform --------------------------------
        result = self._detect_hough(gray, eye_region, roi_w, roi_h)
        if result.confidence >= 0.3:
            self._last_result = result
            return result

        # --- Method 3: darkest region centroid --------------------------------
        result = self._detect_darkest(gray, eye_region, roi_w, roi_h)
        if result.confidence >= 0.1:
            self._last_result = result
            return result

        # --- Method 4: temporal prediction -----------------------------------
        if self._last_result is not None and self._last_result.detected:
            pred = PupilData(
                detected=True,
                center_roi=self._last_result.center_roi,
                center_frame=self._last_result.center_frame,
                diameter_px=self._last_result.diameter_px,
                radius_px=self._last_result.radius_px,
                confidence=0.05,
                method=DetectionMethod.TEMPORAL_PREDICTION,
            )
            return pred

        return PupilData()

    def reset(self) -> None:
        """Clear temporal history — call at the start of a new session."""
        self._last_result = None

    # ------------------------------------------------------------------
    # Image pre-processing
    # ------------------------------------------------------------------

    def _preprocess(self, roi_bgr: np.ndarray) -> np.ndarray:
        """
        Convert to grayscale, apply CLAHE for contrast enhancement,
        then Gaussian blur to reduce sensor noise.
        """
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = self._clahe.apply(gray)
        ksize = self._cfg.pupil_blur_kernel_size
        if ksize % 2 == 0:
            ksize += 1  # Gaussian kernel must be odd
        gray = cv2.GaussianBlur(gray, (ksize, ksize), 0)
        return gray

    # ------------------------------------------------------------------
    # Method 1 — contour-based ellipse fit
    # ------------------------------------------------------------------

    def _detect_contour(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> PupilData:
        """
        Use adaptive thresholding to isolate the dark pupil, then find
        the best-fitting ellipse among the candidate contours.

        Adaptive thresholding is preferred over global because it handles
        uneven illumination (e.g. single-sided desk lamp).
        """
        # Inverse threshold: pupil is dark → becomes white in binary mask
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self._cfg.pupil_adaptive_block_size,
            self._cfg.pupil_adaptive_c,
        )

        # Morphological close to fill small holes in the pupil blob
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return PupilData()

        best_score = -1.0
        best_pupil: Optional[PupilData] = None

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._cfg.pupil_min_area_px or area > self._cfg.pupil_max_area_px:
                continue

            perimeter = cv2.arcLength(cnt, closed=True)
            circularity = contour_circularity(area, perimeter)
            if circularity < self._cfg.pupil_min_circularity:
                continue

            # Need ≥5 points for ellipse fitting
            if len(cnt) < 5:
                continue

            try:
                (cx, cy), (ma, Mi), angle = cv2.fitEllipse(cnt)
            except cv2.error:
                continue

            # Reject degenerate ellipses
            minor_axis = min(ma, Mi)
            major_axis = max(ma, Mi)
            if minor_axis < 2.0:
                continue
            axis_ratio = major_axis / max(minor_axis, 1e-9)
            if axis_ratio > self._cfg.pupil_max_axis_ratio:
                continue

            # Reject centres outside the ROI
            if not (0 <= cx <= roi_w and 0 <= cy <= roi_h):
                continue

            # Composite quality score
            radius = minor_axis / 2.0
            score = circularity * min(1.0, area / (self._cfg.pupil_min_area_px * 10))

            if score > best_score:
                best_score = score
                roi_center = (float(cx), float(cy))
                frame_center = self._roi_to_frame(roi_center, eye, roi_w, roi_h)
                best_pupil = PupilData(
                    detected=True,
                    center_roi=roi_center,
                    center_frame=frame_center,
                    diameter_px=minor_axis,
                    radius_px=radius,
                    ellipse_axes=(major_axis, minor_axis),
                    ellipse_angle_deg=float(angle),
                    confidence=min(score, 0.95),
                    method=DetectionMethod.CONTOUR_ELLIPSE,
                )

        if best_pupil is not None:
            return best_pupil
        return PupilData()

    # ------------------------------------------------------------------
    # Method 2 — Hough circle transform
    # ------------------------------------------------------------------

    def _detect_hough(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> PupilData:
        """
        Apply Hough circle detection. Slower and less accurate than the
        contour method but can find circles when contours are open/partial.
        """
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=self._cfg.hough_dp,
            minDist=self._cfg.hough_min_dist_px,
            param1=self._cfg.hough_param1,
            param2=self._cfg.hough_param2,
            minRadius=self._cfg.hough_min_radius_px,
            maxRadius=self._cfg.hough_max_radius_px,
        )
        if circles is None:
            return PupilData()

        circles = np.round(circles[0, :]).astype(int)
        # Pick the circle nearest to the ROI centre (most likely to be the pupil)
        roi_cx, roi_cy = roi_w / 2.0, roi_h / 2.0
        best_circle = min(circles, key=lambda c: (c[0] - roi_cx) ** 2 + (c[1] - roi_cy) ** 2)

        cx, cy, r = float(best_circle[0]), float(best_circle[1]), float(best_circle[2])
        roi_center = (cx, cy)
        frame_center = self._roi_to_frame(roi_center, eye, roi_w, roi_h)

        return PupilData(
            detected=True,
            center_roi=roi_center,
            center_frame=frame_center,
            diameter_px=r * 2,
            radius_px=r,
            ellipse_axes=(r * 2, r * 2),
            confidence=0.4,
            method=DetectionMethod.HOUGH_CIRCLE,
        )

    # ------------------------------------------------------------------
    # Method 3 — darkest region centroid
    # ------------------------------------------------------------------

    def _detect_darkest(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> PupilData:
        """
        Find the centroid of the darkest region in the ROI.
        Very simple but remarkably robust as a last resort.
        """
        # Find pixels in the lowest-intensity decile
        threshold = int(np.percentile(gray, 10))
        mask = (gray <= threshold).astype(np.uint8) * 255

        # Remove tiny noise blobs
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        moments = cv2.moments(mask)
        if moments["m00"] < 1.0:
            return PupilData()

        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
        roi_center = (float(cx), float(cy))
        frame_center = self._roi_to_frame(roi_center, eye, roi_w, roi_h)

        # Estimate radius from blob area
        area = float(np.sum(mask > 0))
        import math
        radius = math.sqrt(area / math.pi) if area > 0 else 5.0

        return PupilData(
            detected=True,
            center_roi=roi_center,
            center_frame=frame_center,
            diameter_px=radius * 2,
            radius_px=radius,
            confidence=0.15,
            method=DetectionMethod.DARKEST_CENTROID,
        )

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _roi_to_frame(
        self,
        roi_center: Tuple[float, float],
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> Tuple[float, float]:
        """
        Map a point from normalised ROI coordinates back to full-frame pixels.

        The eye ROI was scaled from (eye.roi_w × eye.roi_h) to
        (roi_w × roi_h) during extraction, so we reverse that scaling.
        """
        scale_x = eye.roi_w / roi_w if roi_w > 0 else 1.0
        scale_y = eye.roi_h / roi_h if roi_h > 0 else 1.0
        fx = eye.roi_x + roi_center[0] * scale_x
        fy = eye.roi_y + roi_center[1] * scale_y
        return (float(fx), float(fy))
