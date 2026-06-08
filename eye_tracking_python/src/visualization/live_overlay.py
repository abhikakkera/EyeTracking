"""
Real-time OpenCV overlay renderer.

Draws all detection results onto a copy of the frame:
    • Face bounding box
    • Eye ROI rectangles
    • Pupil centre dots
    • Iris circles (from MediaPipe iris landmarks)
    • Gaze direction arrow
    • Blink indicator
    • Per-frame statistics (FPS, confidence, quality)

All drawing is done on a copy — the original frame is never mutated.
All drawing calls are guarded against None / invalid values.
"""
from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np

from config import AppConfig
from src.data.schema import FrameRecord, IrisData

# Colours (BGR format for OpenCV)
_C_FACE = (0, 255, 0)
_C_EYE = (255, 200, 0)
_C_PUPIL = (0, 0, 255)
_C_IRIS = (0, 200, 255)
_C_GAZE = (255, 0, 255)
_C_BLINK = (0, 165, 255)
_C_TEXT = (255, 255, 255)
_C_GOOD = (0, 220, 0)
_C_QUESTIONABLE = (0, 165, 255)
_C_BAD = (0, 0, 220)

_FONT = cv2.FONT_HERSHEY_SIMPLEX


class LiveOverlay:
    """
    Renders detection results onto a BGR frame.

    Usage:
        overlay = LiveOverlay(config)
        annotated = overlay.draw(frame, record, fps, left_iris, right_iris)
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.overlay

    def draw(
        self,
        frame: np.ndarray,
        record: FrameRecord,
        fps: float = 0.0,
        left_iris: Optional[IrisData] = None,
        right_iris: Optional[IrisData] = None,
        face_bbox: Optional[tuple] = None,
        left_eye_roi: Optional[tuple] = None,
        right_eye_roi: Optional[tuple] = None,
    ) -> np.ndarray:
        """
        Return an annotated copy of the frame.

        Parameters
        ----------
        frame       : BGR image (not mutated)
        record      : FrameRecord for this frame
        fps         : current measured FPS
        left_iris   : optional IrisData for left eye
        right_iris  : optional IrisData for right eye
        face_bbox   : (x, y, w, h) in pixels — optional, can skip
        left_eye_roi  : (x, y, w, h)
        right_eye_roi : (x, y, w, h)
        """
        if not self._cfg.enabled:
            return frame

        out = frame.copy()

        if not record.face_detected:
            self._text(out, "NO FACE DETECTED", (10, 30), scale=0.8, color=_C_BAD)
            self._draw_stats(out, fps, record)
            return out

        # --- Face bounding box -----------------------------------------------
        if self._cfg.show_face_box and face_bbox is not None:
            x, y, w, h = face_bbox
            cv2.rectangle(out, (x, y), (x + w, y + h), _C_FACE, 1)

        # --- Eye ROI boxes ---------------------------------------------------
        if self._cfg.show_eye_roi:
            for roi in [left_eye_roi, right_eye_roi]:
                if roi is not None:
                    rx, ry, rw, rh = roi
                    cv2.rectangle(out, (rx, ry), (rx + rw, ry + rh), _C_EYE, 1)

        # --- Pupil centres ---------------------------------------------------
        if self._cfg.show_pupil_center:
            if record.left_pupil_detected:
                cx, cy = int(record.left_pupil_x), int(record.left_pupil_y)
                r = max(2, int(record.left_pupil_diameter_px / 2))
                cv2.circle(out, (cx, cy), r, _C_PUPIL, 1)
                cv2.circle(out, (cx, cy), 2, _C_PUPIL, -1)
            if record.right_pupil_detected:
                cx, cy = int(record.right_pupil_x), int(record.right_pupil_y)
                r = max(2, int(record.right_pupil_diameter_px / 2))
                cv2.circle(out, (cx, cy), r, _C_PUPIL, 1)
                cv2.circle(out, (cx, cy), 2, _C_PUPIL, -1)

        # --- Iris circles ----------------------------------------------------
        if self._cfg.show_iris_circle:
            for iris in [left_iris, right_iris]:
                if iris is not None and iris.detected and iris.radius_px > 1:
                    cx, cy = int(iris.center_frame[0]), int(iris.center_frame[1])
                    r = int(iris.radius_px)
                    cv2.circle(out, (cx, cy), r, _C_IRIS, 1)

        # --- Gaze arrow ------------------------------------------------------
        if self._cfg.show_gaze_vector and record.face_detected:
            h, w = out.shape[:2]
            # Gaze origin = centre of frame
            ox, oy = w // 2, h // 2
            # Arrow direction from normalised gaze
            dx = (record.gaze_x - 0.5) * w * 0.4
            dy = (record.gaze_y - 0.5) * h * 0.4
            ex, ey = int(ox + dx), int(oy + dy)
            cv2.arrowedLine(out, (ox, oy), (ex, ey), _C_GAZE, 2, tipLength=0.3)

        # --- Blink indicator -------------------------------------------------
        if self._cfg.show_blink_indicator and record.blink_detected:
            self._text(out, "BLINK", (10, 60), scale=0.8, color=_C_BLINK, thickness=2)

        # --- Statistics bar --------------------------------------------------
        self._draw_stats(out, fps, record)

        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _draw_stats(
        self,
        out: np.ndarray,
        fps: float,
        record: FrameRecord,
    ) -> None:
        h, w = out.shape[:2]

        # Quality colour indicator
        quality_color = {
            "good": _C_GOOD,
            "questionable": _C_QUESTIONABLE,
            "bad": _C_BAD,
        }.get(record.frame_quality.value, _C_TEXT)

        lines = []
        if self._cfg.show_fps:
            lines.append(f"FPS: {fps:.1f}")
        if self._cfg.show_confidence:
            lines.append(f"Conf: {record.confidence_score:.2f}  [{record.frame_quality.value}]")
        lines.append(f"Frame: {record.frame_number}")
        lines.append(f"T: {record.timestamp_sec:.2f}s")

        y0 = h - 10 - 18 * len(lines)
        for i, line in enumerate(lines):
            y = y0 + i * 18
            color = quality_color if "Conf" in line else _C_TEXT
            self._text(out, line, (10, y), scale=0.45, color=color)

    @staticmethod
    def _text(
        img: np.ndarray,
        text: str,
        pos: tuple,
        scale: float = 0.5,
        color: tuple = _C_TEXT,
        thickness: int = 1,
    ) -> None:
        cv2.putText(img, text, pos, _FONT, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(img, text, pos, _FONT, scale, color, thickness, cv2.LINE_AA)
