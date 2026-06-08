"""
Central configuration for the eye tracking system.

All thresholds and algorithm parameters are defined here.
Modify this file to tune detection quality without touching algorithm code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

SOFTWARE_VERSION = "0.1.0"


@dataclass
class CameraConfig:
    device_index: int = 0
    target_fps: int = 30
    resolution: Tuple[int, int] = (1280, 720)
    # Keep buffer small for real-time latency
    buffer_size: int = 1


@dataclass
class DetectionConfig:
    # MediaPipe Face Mesh
    mediapipe_min_detection_confidence: float = 0.5
    mediapipe_min_tracking_confidence: float = 0.5
    # refine_landmarks=True enables the iris sub-landmarks (indices 468-477)
    mediapipe_refine_landmarks: bool = True

    # Eye ROI extraction
    eye_roi_padding: float = 0.25    # fraction of eye-box width added as padding
    eye_roi_width: int = 120         # normalised ROI width in pixels
    eye_roi_height: int = 60         # normalised ROI height in pixels

    # Pupil image pre-processing
    pupil_blur_kernel_size: int = 5
    pupil_clahe_clip_limit: float = 2.0
    pupil_clahe_grid_size: Tuple[int, int] = (8, 8)
    pupil_adaptive_block_size: int = 11  # must be odd
    pupil_adaptive_c: int = 6

    # Pupil contour filtering
    pupil_min_area_px: int = 50
    pupil_max_area_px: int = 6000
    pupil_min_circularity: float = 0.25
    pupil_max_axis_ratio: float = 2.5   # major / minor axis limit for ellipse fit

    # Hough circle fallback parameters
    hough_dp: float = 1.2
    hough_min_dist_px: int = 20
    hough_param1: int = 50
    hough_param2: int = 15
    hough_min_radius_px: int = 5
    hough_max_radius_px: int = 35

    # Temporal outlier rejection
    max_pupil_jump_px: float = 50.0   # frame-to-frame jump above this = suspect


@dataclass
class BlinkConfig:
    # EAR (Eye Aspect Ratio) below this threshold → eye considered closed
    ear_closed_threshold: float = 0.21
    # How many consecutive frames EAR must stay below threshold to count as blink
    ear_consec_frames: int = 2
    min_blink_duration_ms: float = 50.0
    max_blink_duration_ms: float = 500.0


@dataclass
class SaccadeConfig:
    # Pixels per second; convert to deg/s using pixels_per_degree
    velocity_threshold_px_per_sec: float = 500.0
    min_duration_ms: float = 10.0
    max_duration_ms: float = 150.0
    min_amplitude_px: float = 5.0
    # Rough estimate; calibrate against known screen/distance after setup
    pixels_per_degree: float = 30.0


@dataclass
class FixationConfig:
    max_dispersion_px: float = 25.0
    min_duration_ms: float = 100.0
    window_size_frames: int = 10   # I-DT sliding window minimum size


@dataclass
class SmoothingConfig:
    # Options: "moving_average" | "exponential" | "savgol" | "kalman"
    method: str = "kalman"
    moving_avg_window: int = 5
    exponential_alpha: float = 0.35    # lower = more smoothing, more lag
    savgol_window: int = 11
    savgol_polyorder: int = 3
    kalman_process_noise: float = 0.01
    kalman_measurement_noise: float = 0.1


@dataclass
class DataConfig:
    output_dir: str = "sessions"
    db_filename: str = "eye_tracking.db"
    auto_create_output_dir: bool = True


@dataclass
class OverlayConfig:
    enabled: bool = True
    show_face_box: bool = True
    show_eye_roi: bool = True
    show_pupil_center: bool = True
    show_iris_circle: bool = True
    show_gaze_vector: bool = True
    show_blink_indicator: bool = True
    show_fps: bool = True
    show_confidence: bool = True

    # BGR colour tuples
    color_face_box: Tuple[int, int, int] = (0, 255, 0)
    color_eye_roi: Tuple[int, int, int] = (255, 200, 0)
    color_pupil: Tuple[int, int, int] = (0, 0, 255)
    color_iris: Tuple[int, int, int] = (0, 200, 255)
    color_gaze: Tuple[int, int, int] = (255, 0, 255)
    color_blink: Tuple[int, int, int] = (0, 165, 255)
    color_text: Tuple[int, int, int] = (255, 255, 255)


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    blink: BlinkConfig = field(default_factory=BlinkConfig)
    saccade: SaccadeConfig = field(default_factory=SaccadeConfig)
    fixation: FixationConfig = field(default_factory=FixationConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    data: DataConfig = field(default_factory=DataConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    log_level: str = "INFO"
    enable_smoothing: bool = True
    # Calibration is off by default; enable after running the calibration routine
    enable_calibration: bool = False


# Module-level singleton — import CONFIG everywhere
CONFIG = AppConfig()
