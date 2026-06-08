"""
Data schema for the eye tracking system — v0.3.

Changes from v0.2:
  - EyeTestType gains PROSACCADE, ANTISACCADE, GAP_OVERLAP
  - FrameRecord gains six camera-distance guidance fields (v0.3):
      camera_distance_status, camera_distance_score,
      distance_guidance_message, face_bbox_width_ratio,
      face_bbox_height_ratio, inter_eye_distance_px

Changes from v0.1 (carried forward):
  - FrameRecord gains quality_flags (List[str]) and raw_pupil_x/y fields
  - SaccadeEvent, FixationEvent, BlinkEvent gain event_id
  - PupilCandidate dataclass added (for debug / scoring inspection)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DetectionMethod(str, Enum):
    MEDIAPIPE_IRIS = "mediapipe_iris"
    CONTOUR_ELLIPSE = "contour_ellipse"
    HOUGH_CIRCLE = "hough_circle"
    DARKEST_CENTROID = "darkest_centroid"
    TEMPORAL_PREDICTION = "temporal_prediction"
    NONE = "none"


class FrameQuality(str, Enum):
    GOOD = "good"
    QUESTIONABLE = "questionable"
    BAD = "bad"


class EyeTestType(str, Enum):
    """Renamed from TestType to avoid pytest collection confusion."""
    FREE_VIEWING = "free_viewing"
    SMOOTH_PURSUIT = "smooth_pursuit"
    SACCADE_TASK = "saccade_task"
    CALIBRATION = "calibration"
    VIDEO_ANALYSIS = "video_analysis"
    # v0.3 structured task modes
    PROSACCADE = "prosaccade"
    ANTISACCADE = "antisaccade"
    GAP_OVERLAP = "gap_overlap"


# Keep backwards-compatible alias
TestType = EyeTestType


# ---------------------------------------------------------------------------
# Camera / frame
# ---------------------------------------------------------------------------

@dataclass
class FrameData:
    """A single captured frame bundled with metadata."""
    image: object              # numpy ndarray (BGR uint8)
    frame_number: int
    timestamp_sec: float       # seconds since session start
    wall_clock: float          # Unix epoch
    fps: float
    width: int
    height: int
    source: str = "unknown"


# ---------------------------------------------------------------------------
# Detection results
# ---------------------------------------------------------------------------

@dataclass
class PupilCandidate:
    """
    One candidate from the contour detection pass.
    Stored in debug mode so you can see exactly why a candidate was or was not chosen.
    """
    center_roi: Tuple[float, float]
    area: float
    circularity: float
    axis_ratio: float
    mean_intensity: float        # mean pixel value inside contour (lower = darker)
    contrast: float              # mean_surrounding - mean_inside (higher = better)
    distance_from_center: float  # distance from ROI centre in pixels
    distance_from_prediction: float  # distance from Kalman/temporal prediction
    score: float                 # final weighted score


@dataclass
class PupilData:
    """Pupil detection result for one eye in one frame."""
    detected: bool = False
    center_roi: Tuple[float, float] = (0.0, 0.0)
    center_frame: Tuple[float, float] = (0.0, 0.0)
    diameter_px: float = 0.0
    radius_px: float = 0.0
    ellipse_axes: Tuple[float, float] = (0.0, 0.0)
    ellipse_angle_deg: float = 0.0
    confidence: float = 0.0
    method: DetectionMethod = DetectionMethod.NONE
    # Debug info (None when debug mode is off)
    candidates: Optional[List[PupilCandidate]] = None


@dataclass
class IrisData:
    """Iris detection result for one eye in one frame."""
    detected: bool = False
    center_frame: Tuple[float, float] = (0.0, 0.0)
    radius_px: float = 0.0
    confidence: float = 0.0


@dataclass
class EyeRegionData:
    """Eye region extracted from the face, including ROI and measurements."""
    detected: bool = False
    roi_image: Optional[object] = None   # numpy ndarray of cropped eye
    roi_x: int = 0
    roi_y: int = 0
    roi_w: int = 0
    roi_h: int = 0
    landmarks_frame: List[Tuple[float, float]] = field(default_factory=list)
    ear: float = 0.0
    is_open: bool = True
    confidence: float = 0.0


@dataclass
class FaceData:
    """Face detection result for one frame."""
    detected: bool = False
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    landmarks: List[Tuple[float, float]] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Gaze estimate
# ---------------------------------------------------------------------------

@dataclass
class GazeData:
    """
    Estimated gaze direction for one frame.
    normalised_x/y ∈ [0, 1]: 0 = left/top, 0.5 = centre, 1 = right/bottom.
    screen_x/y populated after calibration only.
    """
    left_normalized: Tuple[float, float] = (0.5, 0.5)
    right_normalized: Tuple[float, float] = (0.5, 0.5)
    average_normalized: Tuple[float, float] = (0.5, 0.5)
    gaze_vector: Tuple[float, float] = (0.0, 0.0)
    screen_x: Optional[float] = None
    screen_y: Optional[float] = None
    calibrated: bool = False
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Per-frame aggregated record
# ---------------------------------------------------------------------------

@dataclass
class FrameRecord:
    """
    Complete eye tracking record for one frame.
    Written to database, CSV, and JSON.
    """
    session_id: str
    frame_number: int
    timestamp_sec: float

    # Detection flags
    face_detected: bool = False
    left_eye_detected: bool = False
    right_eye_detected: bool = False
    left_pupil_detected: bool = False
    right_pupil_detected: bool = False

    # Raw pupil positions in FRAME PIXEL coordinates
    left_pupil_x: float = 0.0
    left_pupil_y: float = 0.0
    right_pupil_x: float = 0.0
    right_pupil_y: float = 0.0

    # Pupil size
    left_pupil_diameter_px: float = 0.0
    right_pupil_diameter_px: float = 0.0

    # Normalised gaze position [0, 1] within eye bounding box
    left_norm_x: float = 0.5
    left_norm_y: float = 0.5
    right_norm_x: float = 0.5
    right_norm_y: float = 0.5

    # Average gaze (normalised)
    gaze_x: float = 0.5
    gaze_y: float = 0.5

    # Screen coordinates (post-calibration; None if uncalibrated)
    screen_x: Optional[float] = None
    screen_y: Optional[float] = None

    # Smoothed gaze (filled by smoothing module — raw never overwritten)
    smooth_gaze_x: Optional[float] = None
    smooth_gaze_y: Optional[float] = None

    # Eye state
    blink_detected: bool = False
    left_ear: float = 0.0
    right_ear: float = 0.0

    # Kinematics — computed in pixel space using actual pupil coordinates
    # (NOT normalised gaze — see Bug 1 fix in v0.2)
    gaze_velocity_px_per_sec: float = 0.0
    gaze_acceleration_px_per_sec2: float = 0.0
    gaze_jerk_px_per_sec3: float = 0.0

    # Quality
    confidence_score: float = 0.0
    frame_quality: FrameQuality = FrameQuality.GOOD
    blur_score: float = 0.0
    # Human-readable flags, e.g. ["low_light", "blink", "unrealistic_jump"]
    quality_flags: List[str] = field(default_factory=list)

    # Detection methods used
    left_detection_method: DetectionMethod = DetectionMethod.NONE
    right_detection_method: DetectionMethod = DetectionMethod.NONE

    # Camera distance guidance (v0.3) — populated by DistanceEstimator each frame.
    # status: "good" | "too_close" | "too_far" | "unknown"
    camera_distance_status: str = "unknown"
    camera_distance_score: float = 0.0       # 0–1; 1.0 = centered in good range
    distance_guidance_message: str = ""
    face_bbox_width_ratio: float = 0.0       # face bbox width / frame width
    face_bbox_height_ratio: float = 0.0      # face bbox height / frame height
    inter_eye_distance_px: float = 0.0       # pixel distance between eye centres


# ---------------------------------------------------------------------------
# Eye movement events
# ---------------------------------------------------------------------------

@dataclass
class SaccadeEvent:
    session_id: str
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_ms: float
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    amplitude_px: float
    peak_velocity_px_per_sec: float
    mean_velocity_px_per_sec: float = 0.0
    direction_deg: float = 0.0
    confidence: float = 1.0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class FixationEvent:
    session_id: str
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_ms: float
    center_x: float
    center_y: float
    dispersion_px: float
    num_frames: int = 0
    confidence: float = 1.0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class BlinkEvent:
    session_id: str
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_ms: float
    affected_eye: str   # "left" | "right" | "both"
    confidence: float = 1.0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------

@dataclass
class SessionMetadata:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject_id: str = "anonymous"
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0
    camera_type: str = "webcam"
    camera_resolution: Tuple[int, int] = (0, 0)
    fps: float = 0.0
    calibration_used: bool = False
    calibration_points: int = 0
    test_type: EyeTestType = EyeTestType.FREE_VIEWING
    software_version: str = "0.2.0"
    total_frames: int = 0
    good_frames: int = 0
    blink_count: int = 0
    saccade_count: int = 0
    fixation_count: int = 0
    notes: str = ""
