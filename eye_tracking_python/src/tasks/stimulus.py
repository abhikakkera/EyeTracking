"""
OpenCV stimulus renderer for structured eye-movement tasks — v0.3.

Draws fixation dots, peripheral targets, and blank screens on a dark
background numpy canvas.  No PyQt/pygame dependency — pure cv2 + numpy.

Usage:
    renderer = StimulusRenderer()
    canvas = renderer.render(1280, 720, state)
    cv2.imshow("task", canvas)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from src.tasks.task_schema import TaskPhase


@dataclass
class StimulusState:
    """
    What the stimulus renderer should draw for the current frame.
    Populated by the active task on every call to current_context().
    """
    phase: TaskPhase = TaskPhase.WAITING

    # Fixation dot
    show_fixation: bool = False
    fixation_x: float = 0.5       # normalized [0, 1]
    fixation_y: float = 0.5
    fixation_size_px: int = 10
    fixation_color: Tuple[int, int, int] = (255, 255, 255)  # BGR white

    # Target dot
    show_target: bool = False
    target_x: float = 0.5         # normalized [0, 1]
    target_y: float = 0.5
    target_size_px: int = 18
    target_color: Tuple[int, int, int] = (255, 255, 255)

    # Canvas background
    bg_color: Tuple[int, int, int] = (30, 30, 30)

    # Optional status text drawn in corner
    status_text: str = ""
    trial_text: str = ""


class StimulusRenderer:
    """
    Renders task stimuli on a numpy BGR canvas.

    All coordinates in the returned canvas are in pixels.
    """

    _FONT = cv2.FONT_HERSHEY_SIMPLEX

    def render(self, width: int, height: int, state: StimulusState) -> np.ndarray:
        """
        Render stimulus for the current frame.

        Parameters
        ----------
        width, height : canvas size in pixels
        state         : current stimulus state

        Returns
        -------
        np.ndarray — BGR uint8 of shape (height, width, 3)
        """
        canvas = np.full((height, width, 3), state.bg_color, dtype=np.uint8)

        # ---- Fixation dot ---------------------------------------------------
        if state.show_fixation:
            fx = int(state.fixation_x * width)
            fy = int(state.fixation_y * height)
            r  = state.fixation_size_px
            cv2.circle(canvas, (fx, fy), r + 2, (0, 0, 0), -1)       # black outline
            cv2.circle(canvas, (fx, fy), r,     state.fixation_color, -1)
            cv2.circle(canvas, (fx, fy), r,     (0, 0, 0), 1)         # thin border

        # ---- Target dot -----------------------------------------------------
        if state.show_target:
            tx = int(state.target_x * width)
            ty = int(state.target_y * height)
            r  = state.target_size_px
            cv2.circle(canvas, (tx, ty), r + 2, (0, 0, 0), -1)
            cv2.circle(canvas, (tx, ty), r,     state.target_color, -1)
            cv2.circle(canvas, (tx, ty), r,     (0, 0, 0), 1)

        # ---- Status / trial text (top-left corner) --------------------------
        if state.trial_text:
            _draw_text(canvas, state.trial_text, (12, 30),
                       color=(180, 180, 180), scale=0.60)

        if state.status_text:
            _draw_text(canvas, state.status_text, (12, 58),
                       color=(130, 200, 130), scale=0.52)

        # ---- Phase watermark for WAITING / DONE ----------------------------
        if state.phase == TaskPhase.WAITING:
            _center_text(canvas, "Get ready ...", scale=0.80,
                         color=(160, 160, 160))
        elif state.phase == TaskPhase.DONE:
            _center_text(canvas, "Session complete", scale=0.90,
                         color=(100, 220, 100))

        return canvas

    def render_distance_overlay(
        self,
        canvas: np.ndarray,
        status: str,
        message: str,
        score: float,
    ) -> np.ndarray:
        """
        Draw a small camera-distance guidance bar in the top-right corner.

        Parameters
        ----------
        canvas  : stimulus canvas (modified in place)
        status  : "good" | "too_close" | "too_far" | "unknown"
        message : one-line guidance message
        score   : 0–1 quality score

        Returns the modified canvas (same array).
        """
        if status == "good" and not message:
            return canvas

        h, w = canvas.shape[:2]
        bar_x = w - 310
        bar_y = 12

        # Bar background
        cv2.rectangle(canvas, (bar_x - 4, bar_y - 4),
                      (w - 6, bar_y + 40), (50, 50, 50), -1)

        # Status icon
        if status == "too_close":
            icon_color = (50, 50, 220)   # red-ish
            icon = "◀  Too close"
        elif status == "too_far":
            icon_color = (50, 165, 255)  # orange
            icon = "▶  Move closer"
        elif status == "good":
            icon_color = (50, 200, 50)   # green
            icon = "✓  Good distance"
        else:
            icon_color = (160, 160, 160)
            icon = "?  Face not found"

        _draw_text(canvas, icon, (bar_x, bar_y + 18),
                   color=icon_color, scale=0.55, thick=1)

        # Quality bar
        bw = 290
        bh = 6
        filled = int(bw * max(0.0, min(1.0, score)))
        bar_c = icon_color
        cv2.rectangle(canvas, (bar_x, bar_y + 28),
                      (bar_x + bw, bar_y + 28 + bh), (80, 80, 80), -1)
        if filled > 0:
            cv2.rectangle(canvas, (bar_x, bar_y + 28),
                          (bar_x + filled, bar_y + 28 + bh), bar_c, -1)

        return canvas


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _draw_text(
    img: np.ndarray,
    text: str,
    xy: Tuple[int, int],
    color: Tuple[int, int, int] = (220, 220, 220),
    scale: float = 0.55,
    thick: int = 1,
    font: int = cv2.FONT_HERSHEY_SIMPLEX,
) -> None:
    """Draw text with a thin black shadow for legibility on any background."""
    cv2.putText(img, text, xy, font, scale, (0, 0, 0), thick + 2)
    cv2.putText(img, text, xy, font, scale, color,    thick)


def _center_text(
    img: np.ndarray,
    text: str,
    scale: float = 0.80,
    color: Tuple[int, int, int] = (200, 200, 200),
    font: int = cv2.FONT_HERSHEY_SIMPLEX,
) -> None:
    """Draw text horizontally centred in img."""
    h, w = img.shape[:2]
    (tw, th), _ = cv2.getTextSize(text, font, scale, 1)
    x = (w - tw) // 2
    y = h // 2 + th // 2
    cv2.putText(img, text, (x, y), font, scale, (0, 0, 0), 3)
    cv2.putText(img, text, (x, y), font, scale, color,     1)
