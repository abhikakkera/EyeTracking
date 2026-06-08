"""
Pupil detector — v0.2 (multi-signal weighted candidate scoring).

v0.1 flaw: candidate score = circularity × area_ratio.
  This ignores darkness, contrast, and temporal consistency.
  A bright circular highlight scored identically to a dark pupil.

v0.2 fix: each contour candidate is scored on 7 signals:
  1. darkness      — mean pixel intensity inside contour (lower = better)
  2. circularity   — 4π·area / perimeter²
  3. contrast      — mean(surrounding ring) - mean(inside) (higher = better)
  4. size          — area relative to expected pupil size
  5. shape         — ellipse axis ratio (1.0 = perfect circle)
  6. center_dist   — distance from ROI centre (soft prior only)
  7. temporal      — distance from predicted position (previous frame)

Each signal is normalised to [0, 1] and combined with configurable weights
defined in PupilScoringConfig.

Hard rejection filters (applied BEFORE scoring):
  - Area outside [min_area, max_area]
  - Circularity < min_circularity
  - Mean intensity > max_mean_intensity  (rejects bright reflections)
  - Axis ratio > max_axis_ratio
  - Centre outside ROI

The four-level fallback hierarchy is preserved for when contour detection
fails completely, but the ordering now reflects confidence accurately:
  1. Contour + ellipse fit (primary, scored)
  2. Hough circle transform (fallback)
  3. Darkest-region centroid (last geometric resort)
  4. Temporal prediction (only if all geometric methods fail)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import AppConfig
from src.data.schema import DetectionMethod, EyeRegionData, PupilCandidate, PupilData
from src.utils.geometry import contour_circularity, euclidean_distance

logger = logging.getLogger(__name__)


class PupilDetector:
    """
    Stateful pupil detector that uses multi-signal scoring to select the best
    candidate from each frame, with temporal prediction as a last resort.

    Maintain one instance per eye per session.
    Call reset() between sessions.

    Usage:
        detector = PupilDetector(config)
        pupil = detector.detect(eye_region)
    """

    def __init__(self, config: AppConfig) -> None:
        self._det_cfg = config.detection
        self._score_cfg = config.pupil_scoring
        self._debug = config.debug.enabled

        self._last_result: Optional[PupilData] = None
        # Temporal prediction: keep a short position history
        self._position_history: List[Tuple[float, float]] = []
        self._history_maxlen: int = config.temporal.history_frames

        self._clahe = cv2.createCLAHE(
            clipLimit=self._det_cfg.pupil_clahe_clip_limit,
            tileGridSize=self._det_cfg.pupil_clahe_grid_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, eye_region: EyeRegionData) -> PupilData:
        """
        Detect pupil in one eye ROI.  Never raises.
        Returns PupilData with detected=False when all methods fail.
        """
        if not eye_region.detected or eye_region.roi_image is None:
            return PupilData()

        try:
            gray = self._preprocess(eye_region.roi_image)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pupil pre-processing failed: %s", exc)
            return PupilData()

        roi_h, roi_w = gray.shape[:2]
        predicted_roi = self._predicted_roi_pos(eye_region, roi_w, roi_h)

        # Method 1 — multi-signal contour scoring (primary)
        result = self._detect_contour(gray, eye_region, roi_w, roi_h, predicted_roi)
        if result.confidence >= 0.45:
            self._record_result(result)
            return result

        # Method 2 — Hough circle (fallback when contours are fragmented)
        result = self._detect_hough(gray, eye_region, roi_w, roi_h, predicted_roi)
        if result.confidence >= 0.25:
            self._record_result(result)
            return result

        # Method 3 — darkest centroid (last geometric attempt)
        result = self._detect_darkest(gray, eye_region, roi_w, roi_h)
        if result.confidence >= 0.08:
            self._record_result(result)
            return result

        # Method 4 — temporal prediction
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
        self._last_result = None
        self._position_history.clear()

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------

    def _preprocess(self, roi_bgr: np.ndarray) -> np.ndarray:
        """
        Grayscale → CLAHE (contrast enhancement) → Gaussian blur (noise reduction).
        CLAHE is the most important step: it normalises local contrast so that
        the pupil boundary remains detectable under uneven lighting.
        """
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = self._clahe.apply(gray)
        k = self._det_cfg.pupil_blur_kernel_size
        if k % 2 == 0:
            k += 1
        return cv2.GaussianBlur(gray, (k, k), 0)

    # ------------------------------------------------------------------
    # Method 1 — multi-signal contour scoring
    # ------------------------------------------------------------------

    def _detect_contour(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
        predicted_roi: Optional[Tuple[float, float]],
    ) -> PupilData:
        """
        Threshold → contours → score each candidate → return best.

        Key difference from v0.1: the scoring function rejects bright regions
        (corneal reflections, glasses glare) before scoring, and weights
        darkness and contrast heavily.
        """
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self._det_cfg.pupil_adaptive_block_size,
            self._det_cfg.pupil_adaptive_c,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return PupilData()

        candidates: List[Tuple[float, PupilData, PupilCandidate]] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._det_cfg.pupil_min_area_px or area > self._det_cfg.pupil_max_area_px:
                continue

            perimeter = cv2.arcLength(cnt, closed=True)
            circularity = contour_circularity(area, perimeter)
            if circularity < self._det_cfg.pupil_min_circularity:
                continue

            if len(cnt) < 5:
                continue

            try:
                (cx, cy), (ma, mi), angle = cv2.fitEllipse(cnt)
            except cv2.error:
                continue

            minor_ax = min(ma, mi)
            major_ax = max(ma, mi)
            if minor_ax < 2.0:
                continue

            axis_ratio = major_ax / max(minor_ax, 1e-9)
            if axis_ratio > self._det_cfg.pupil_max_axis_ratio:
                continue

            # Hard-reject if centre falls outside ROI
            if not (0 <= cx <= roi_w and 0 <= cy <= roi_h):
                continue

            # ------- DARKNESS CHECK (v0.1 was missing this) --------
            # Create a mask for this contour and measure mean intensity.
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            mean_inside = float(cv2.mean(gray, mask=mask)[0])

            # Hard-reject bright regions (reflections, highlights)
            if mean_inside > self._det_cfg.pupil_max_mean_intensity:
                continue

            # -------- CONTRAST CHECK --------------------------------
            # Dilate the mask to get a surrounding ring, then measure contrast.
            ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
            dilated = cv2.dilate(mask, ring_kernel, iterations=1)
            ring_mask = cv2.subtract(dilated, mask)
            mean_ring = float(cv2.mean(gray, mask=ring_mask)[0])
            contrast = mean_ring - mean_inside

            if contrast < self._det_cfg.pupil_min_contrast:
                continue

            # -------- SCORE -----------------------------------------
            roi_center = (float(cx), float(cy))
            dist_from_center = math.hypot(cx - roi_w / 2, cy - roi_h / 2)

            if predicted_roi is not None:
                dist_from_pred = euclidean_distance(roi_center, predicted_roi)
            else:
                dist_from_pred = 0.0

            candidate_info = PupilCandidate(
                center_roi=roi_center,
                area=area,
                circularity=circularity,
                axis_ratio=axis_ratio,
                mean_intensity=mean_inside,
                contrast=contrast,
                distance_from_center=dist_from_center,
                distance_from_prediction=dist_from_pred,
                score=0.0,   # filled below
            )

            score = self._score_candidate(
                candidate_info, roi_w, roi_h, predicted_roi is not None
            )
            candidate_info = PupilCandidate(
                **{**candidate_info.__dict__, "score": score}
            )

            frame_center = self._roi_to_frame(roi_center, eye, roi_w, roi_h)
            pupil = PupilData(
                detected=True,
                center_roi=roi_center,
                center_frame=frame_center,
                diameter_px=minor_ax,
                radius_px=minor_ax / 2.0,
                ellipse_axes=(major_ax, minor_ax),
                ellipse_angle_deg=float(angle),
                confidence=min(score, 0.95),
                method=DetectionMethod.CONTOUR_ELLIPSE,
                candidates=[candidate_info] if self._debug else None,
            )
            candidates.append((score, pupil, candidate_info))

        if not candidates:
            return PupilData()

        # Sort by score descending and pick the best
        candidates.sort(key=lambda t: t[0], reverse=True)
        best_score, best_pupil, _ = candidates[0]

        # In debug mode, attach all candidates to the winning PupilData
        if self._debug and best_pupil.candidates is not None:
            all_infos = [c for _, _, c in candidates]
            best_pupil = PupilData(
                **{**best_pupil.__dict__, "candidates": all_infos}
            )

        return best_pupil

    def _score_candidate(
        self,
        c: PupilCandidate,
        roi_w: int,
        roi_h: int,
        has_prediction: bool,
    ) -> float:
        """
        Compute a weighted composite score ∈ [0, 1] for a pupil candidate.

        Each signal is independently normalised to [0, 1] so that weights
        are directly comparable.
        """
        cfg = self._score_cfg

        # 1. Darkness: lower intensity = darker pupil = better
        #    Normalise: 0 intensity → 1.0; max_mean_intensity → 0.0
        darkness = 1.0 - (c.mean_intensity / self._det_cfg.pupil_max_mean_intensity)
        darkness = max(0.0, min(1.0, darkness))

        # 2. Circularity (already 0-1, 1.0 = perfect circle)
        circularity = min(1.0, c.circularity)

        # 3. Contrast: saturate at 80 intensity units
        contrast = min(1.0, c.contrast / 80.0)

        # 4. Size: expected pupil occupies ~5% of ROI area
        roi_area = roi_w * roi_h
        expected_area = roi_area * cfg.expected_area_fraction
        size_deviation = abs(c.area - expected_area) / max(expected_area, 1.0)
        size = max(0.0, 1.0 - size_deviation)

        # 5. Shape: axis_ratio 1.0 = perfect; penalise elongation
        shape = max(0.0, 1.0 - (c.axis_ratio - 1.0) / self._det_cfg.pupil_max_axis_ratio)

        # 6. Distance from ROI centre (soft prior — pupils can be off-centre)
        max_dist = math.hypot(roi_w, roi_h) / 2.0
        center_dist = max(0.0, 1.0 - c.distance_from_center / max(max_dist, 1.0))

        # 7. Temporal consistency: close to predicted position
        if has_prediction and c.distance_from_prediction > 0:
            temporal = max(
                0.0,
                1.0 - c.distance_from_prediction / self._det_cfg.max_pupil_jump_px,
            )
        else:
            temporal = 0.5   # neutral when no prediction is available

        # Weighted sum
        total_weight = (
            cfg.weight_darkness +
            cfg.weight_circularity +
            cfg.weight_contrast +
            cfg.weight_size +
            cfg.weight_shape +
            cfg.weight_center_dist +
            cfg.weight_temporal
        )
        score = (
            cfg.weight_darkness    * darkness +
            cfg.weight_circularity * circularity +
            cfg.weight_contrast    * contrast +
            cfg.weight_size        * size +
            cfg.weight_shape       * shape +
            cfg.weight_center_dist * center_dist +
            cfg.weight_temporal    * temporal
        ) / max(total_weight, 1e-9)

        return float(score)

    # ------------------------------------------------------------------
    # Method 2 — Hough circle transform
    # ------------------------------------------------------------------

    def _detect_hough(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
        predicted_roi: Optional[Tuple[float, float]],
    ) -> PupilData:
        """
        Hough circles: useful when the pupil boundary is partially occluded
        (droopy eyelid, glasses frame) so the contour is open.
        Pick the circle nearest to the predicted position, or ROI centre.
        """
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT,
            dp=self._det_cfg.hough_dp,
            minDist=self._det_cfg.hough_min_dist_px,
            param1=self._det_cfg.hough_param1,
            param2=self._det_cfg.hough_param2,
            minRadius=self._det_cfg.hough_min_radius_px,
            maxRadius=self._det_cfg.hough_max_radius_px,
        )
        if circles is None:
            return PupilData()

        circles = np.round(circles[0, :]).astype(int)

        # Anchor: use temporal prediction if available, else ROI centre
        anchor = predicted_roi if predicted_roi is not None else (roi_w / 2.0, roi_h / 2.0)
        best = min(circles, key=lambda c: (c[0] - anchor[0]) ** 2 + (c[1] - anchor[1]) ** 2)

        cx, cy, r = float(best[0]), float(best[1]), float(best[2])

        # Basic darkness check on Hough result
        mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.circle(mask, (int(cx), int(cy)), max(1, int(r)), 255, -1)
        mean_inside = float(cv2.mean(gray, mask=mask)[0])
        if mean_inside > self._det_cfg.pupil_max_mean_intensity * 1.2:
            return PupilData()   # too bright — probably a reflection

        roi_center = (cx, cy)
        frame_center = self._roi_to_frame(roi_center, eye, roi_w, roi_h)
        return PupilData(
            detected=True,
            center_roi=roi_center,
            center_frame=frame_center,
            diameter_px=r * 2,
            radius_px=r,
            ellipse_axes=(r * 2, r * 2),
            confidence=0.30,
            method=DetectionMethod.HOUGH_CIRCLE,
        )

    # ------------------------------------------------------------------
    # Method 3 — darkest-region centroid
    # ------------------------------------------------------------------

    def _detect_darkest(
        self,
        gray: np.ndarray,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> PupilData:
        """Last geometric resort. Finds the centroid of the darkest 10% of pixels."""
        threshold = int(np.percentile(gray, 10))
        mask = (gray <= threshold).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        moments = cv2.moments(mask)
        if moments["m00"] < 1.0:
            return PupilData()

        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]

        # Additional sanity: centroid must be reasonably dark
        gray_val = float(gray[min(int(cy), roi_h - 1), min(int(cx), roi_w - 1)])
        if gray_val > self._det_cfg.pupil_max_mean_intensity * 1.5:
            return PupilData()

        area = float(np.sum(mask > 0))
        radius = math.sqrt(area / math.pi) if area > 0 else 5.0

        roi_center = (float(cx), float(cy))
        return PupilData(
            detected=True,
            center_roi=roi_center,
            center_frame=self._roi_to_frame(roi_center, eye, roi_w, roi_h),
            diameter_px=radius * 2,
            radius_px=radius,
            confidence=0.10,
            method=DetectionMethod.DARKEST_CENTROID,
        )

    # ------------------------------------------------------------------
    # Temporal helpers
    # ------------------------------------------------------------------

    def _predicted_roi_pos(
        self,
        eye: EyeRegionData,
        roi_w: int,
        roi_h: int,
    ) -> Optional[Tuple[float, float]]:
        """
        Predict the pupil position in ROI coordinates using the last known frame result.
        Returns None if no history exists.
        """
        if self._last_result is None or not self._last_result.detected:
            return None
        # Map last frame-space position back to current ROI space
        scale_x = roi_w / eye.roi_w if eye.roi_w > 0 else 1.0
        scale_y = roi_h / eye.roi_h if eye.roi_h > 0 else 1.0
        fx, fy = self._last_result.center_frame
        px = (fx - eye.roi_x) * scale_x
        py = (fy - eye.roi_y) * scale_y
        if 0 <= px <= roi_w and 0 <= py <= roi_h:
            return (px, py)
        return None

    def _record_result(self, pupil: PupilData) -> None:
        self._last_result = pupil
        if len(self._position_history) >= self._history_maxlen:
            self._position_history.pop(0)
        self._position_history.append(pupil.center_frame)

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
        Map a pixel position in the normalised ROI back to full-frame pixels.
        The ROI was resized from (eye.roi_w × eye.roi_h) to (roi_w × roi_h),
        so we reverse that scale then add the ROI origin offset.
        """
        scale_x = eye.roi_w / roi_w if roi_w > 0 else 1.0
        scale_y = eye.roi_h / roi_h if roi_h > 0 else 1.0
        return (
            float(eye.roi_x + roi_center[0] * scale_x),
            float(eye.roi_y + roi_center[1] * scale_y),
        )
