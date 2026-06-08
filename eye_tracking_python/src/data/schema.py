"""
Data schema for the eye tracking system.

Every inter-module data transfer uses the typed dataclasses defined here.
This single source of truth for field names makes CSV/JSON export and future
ML pipeline integration straightforward and consistent.
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


class TestType(str, Enum):
    FREE_VIEWING = "free_viewing"
    SMOOTH_PURSUIT = "smooth_pursuit"
    SACCADE_TASK = "saccade_task"
    CALIBRATION = "calibration"
    VIDEO_ANALYSIS = "video_analysis"


# ---------------------------------------------------------------------------
# Camera / frame wrapper
# ---------------------------------------------------------------------------

@dataclass
class FrameData:
    """A single captured frame bundled with metadata."""
    image: object              # numpy ndarray (BGR uint8)
    frame_number: int
    timestamp_sec: float       # seconds since session start (or video offset)
    wall_clock: float          # Unix epoch time
    fps: float
    width: int
    height: int
    source: str = "unknown"    # "webcam" | "video_file" | filesystem path


# ---------------------------------------------------------------------------
# Detection sub-results
# ---------------------------------------------------------------------------

@dataclass
class PupilData:
    """Pupil detection result for one eye in one frame."""
    detected: bool = False
    center_roi: Tuple[float, float] = (0.0, 0.0)    # within eye-ROI coords
    center_frame: Tuple[float, float] = (0.0, 0.0)  # full-frame coords
    diameter_px: float = 0.0
    radius_px: float = 0.0
    ellipse_axes: Tuple[float, float] = (0.0, 0.0)  # (major_axis, minor_axis)
    ellipse_angle_deg: float = 0.0
    confidence: float = 0.0
    method: DetectionMethod = DetectionMethod.NONE


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
    roi_image: Optional[object] = None   # numpy ndarray of the cropped eye
    roi_x: int = 0       # top-left corner of ROI in full-frame pixel coords
    roi_y: int = 0
    roi_w: int = 0
    roi_h: int = 0
    landmarks_frame: List[Tuple[float, float]] = field(default_factory=list)
    ear: float = 0.0     # eye aspect ratio (Soukupova & Cech 2016)
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
    # Full 468 (+ optional 10 iris) MediaPipe landmarks in pixel coords
    landmarks: List[Tuple[float, float]] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Gaze estimate
# ---------------------------------------------------------------------------

@dataclass
class GazeData:
    """
    Estimated gaze direction for one frame.

    normalized_x / normalized_y ∈ [0, 1] within the eye bounding box:
        0.0 = left/top edge,  0.5 = center,  1.0 = right/bottom edge.
    screen_x / screen_y are populated only after calibration.
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
# Aggregated per-frame record (written to storage)
# ---------------------------------------------------------------------------

@dataclass
class FrameRecord:
    """
    Complete eye tracking record for one frame.
    This is what gets persisted to the database and exported to CSV/JSON.
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

    # Raw pupil positions (full-frame pixel coords)
    left_pupil_x: float = 0.0
    left_pupil_y: float = 0.0
    right_pupil_x: float = 0.0
    right_pupil_y: float = 0.0

    # Pupil size
    left_pupil_diameter_px: float = 0.0
    right_pupil_diameter_px: float = 0.0

    # Normalised gaze position [0, 1]
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

    # Smoothed gaze (filled by the smoothing module)
    smooth_gaze_x: Optional[float] = None
    smooth_gaze_y: Optional[float] = None

    # Eye state
    blink_detected: bool = False
    left_ear: float = 0.0
    right_ear: float = 0.0

    # Kinematics (filled by MovementAnalyzer)
    gaze_velocity_px_per_sec: float = 0.0
    gaze_acceleration: float = 0.0

    # Quality indicators
    confidence_score: float = 0.0
    frame_quality: FrameQuality = FrameQuality.GOOD
    blur_score: float = 0.0

    # Which detection method was used per eye
    left_detection_method: DetectionMethod = DetectionMethod.NONE
    right_detection_method: DetectionMethod = DetectionMethod.NONE


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
    direction_deg: float
    confidence: float = 1.0


@dataclass
class FixationEvent:
    session_id: str
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_ms: float
    center_x: float
    center_y: float
    dispersion_px: float
    confidence: float = 1.0


@dataclass
class BlinkEvent:
    session_id: str
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_ms: float
    affected_eye: str   # "left" | "right" | "both"
    confidence: float = 1.0


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
    test_type: TestType = TestType.FREE_VIEWING
    software_version: str = "0.1.0"
    total_frames: int = 0
    good_frames: int = 0
    blink_count: int = 0
    saccade_count: int = 0
    fixation_count: int = 0
    notes: str = ""
