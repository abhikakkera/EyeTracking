"""
Geometric helper functions used across the detection and tracking modules.
All functions operate on plain Python floats or NumPy arrays — no domain objects.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


Point2D = Tuple[float, float]


def euclidean_distance(p1: Point2D, p2: Point2D) -> float:
    """Return the Euclidean distance between two 2-D points."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def midpoint(p1: Point2D, p2: Point2D) -> Point2D:
    """Return the midpoint of two 2-D points."""
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def contour_circularity(area: float, perimeter: float) -> float:
    """
    Circularity = 4π · area / perimeter².
    Perfect circle → 1.0. More irregular → lower value.
    Used to filter non-pupil contours during pupil detection.
    """
    if perimeter <= 0.0:
        return 0.0
    return (4.0 * math.pi * area) / (perimeter ** 2)


def eye_aspect_ratio(landmarks: List[Point2D]) -> float:
    """
    Calculate the Eye Aspect Ratio (EAR) from six eye-lid landmarks.

    Soukupova & Cech (2016) formula:
        EAR = (‖P2-P6‖ + ‖P3-P5‖) / (2 · ‖P1-P4‖)

    Landmark order (OpenCV convention, left→right, top→bottom):
        P1 = left corner
        P2 = upper-left lid
        P3 = upper-right lid
        P4 = right corner
        P5 = lower-right lid
        P6 = lower-left lid

    EAR ≈ 0.3 for a wide-open eye; drops below 0.21 during a blink.
    """
    if len(landmarks) != 6:
        raise ValueError(f"EAR requires exactly 6 landmarks, got {len(landmarks)}")
    p1, p2, p3, p4, p5, p6 = landmarks
    vert_a = euclidean_distance(p2, p6)
    vert_b = euclidean_distance(p3, p5)
    horiz = euclidean_distance(p1, p4)
    if horiz < 1e-9:
        return 0.0
    return (vert_a + vert_b) / (2.0 * horiz)


def normalize_point_in_box(
    point: Point2D,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
) -> Point2D:
    """
    Map a point to [0, 1] within a bounding box.

    0.0 = left/top edge, 1.0 = right/bottom edge.
    Returns (0.5, 0.5) if the box has zero area to avoid division by zero.
    """
    if box_w < 1e-9 or box_h < 1e-9:
        return (0.5, 0.5)
    nx = (point[0] - box_x) / box_w
    ny = (point[1] - box_y) / box_h
    return (float(np.clip(nx, 0.0, 1.0)), float(np.clip(ny, 0.0, 1.0)))


def compute_velocity(
    pos_prev: Point2D,
    pos_curr: Point2D,
    dt: float,
) -> Tuple[float, float, float]:
    """
    Compute the velocity vector and scalar speed between two frames.

    Returns:
        (vx, vy, speed)  — vx, vy in pixels/sec; speed = ‖(vx, vy)‖.
    """
    if dt < 1e-9:
        return (0.0, 0.0, 0.0)
    vx = (pos_curr[0] - pos_prev[0]) / dt
    vy = (pos_curr[1] - pos_prev[1]) / dt
    speed = math.hypot(vx, vy)
    return (vx, vy, speed)


def compute_angle_deg(dx: float, dy: float) -> float:
    """
    Return the direction angle of a 2-D displacement vector in degrees [0, 360).
    dy is negated because screen Y increases downward.
    """
    angle = math.degrees(math.atan2(-dy, dx))
    return angle % 360.0


def estimate_circle_from_points(
    points: np.ndarray,
) -> Tuple[Point2D, float]:
    """
    Least-squares circle fit for a set of N×2 points.
    Uses the algebraic method (Kaasa & Ummels).
    Falls back to centroid + mean distance if the system is ill-conditioned.

    Returns: ((cx, cy), radius)
    """
    if len(points) < 3:
        cx = float(np.mean(points[:, 0]))
        cy = float(np.mean(points[:, 1]))
        dists = np.linalg.norm(points - np.array([cx, cy]), axis=1)
        return (cx, cy), float(np.mean(dists))

    x = points[:, 0].astype(np.float64)
    y = points[:, 1].astype(np.float64)
    A = np.column_stack([x, y, np.ones(len(x))])
    b = x ** 2 + y ** 2
    try:
        result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        cx = result[0] / 2.0
        cy = result[1] / 2.0
        r_sq = result[2] + cx ** 2 + cy ** 2
        r = math.sqrt(max(r_sq, 0.0))
        return (float(cx), float(cy)), float(r)
    except np.linalg.LinAlgError:
        cx_f = float(np.mean(x))
        cy_f = float(np.mean(y))
        dists = np.sqrt((x - cx_f) ** 2 + (y - cy_f) ** 2)
        return (cx_f, cy_f), float(np.mean(dists))


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def image_blur_score(gray: np.ndarray) -> float:
    """
    Estimate image sharpness via variance of the Laplacian.
    Higher = sharper.  Values below ~50 suggest significant blur.
    """
    import cv2
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dispersion(points: List[Point2D]) -> float:
    """
    Compute I-DT dispersion: (max_x - min_x) + (max_y - min_y).
    Used by the fixation detector.
    """
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))
