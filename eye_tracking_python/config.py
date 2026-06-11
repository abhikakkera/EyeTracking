"""
Central configuration for the eye tracking system.

Every algorithm threshold lives here.  Change values here; never hard-code
magic numbers in algorithm files.

v0.2 additions:
  - PupilScoringConfig   — per-signal weights for multi-signal candidate scoring
  - TemporalConfig       — outlier rejection and confidence-decay parameters
  - QualityConfig        — frame quality flag thresholds
  - DebugConfig          — debug mode output paths
  - velocity now in pixel space (renamed threshold field)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

SOFTWARE_VERSION = "0.3.0"


@dataclass
class CameraConfig:
    device_index: int = 0
    target_fps: int = 30
    resolution: Tuple[int, int] = (1280, 720)
    buffer_size: int = 1


@dataclass
class DetectionConfig:
    # MediaPipe Face Mesh (Tasks API)
    mediapipe_min_detection_confidence: float = 0.5
    mediapipe_min_tracking_confidence: float = 0.5
    mediapipe_refine_landmarks: bool = True

    # Eye ROI extraction
    eye_roi_padding: float = 0.25
    eye_roi_width: int = 120
    eye_roi_height: int = 60

    # Pupil image preprocessing
    pupil_blur_kernel_size: int = 5
    pupil_clahe_clip_limit: float = 2.0
    pupil_clahe_grid_size: Tuple[int, int] = (8, 8)
    pupil_adaptive_block_size: int = 11   # must be odd
    pupil_adaptive_c: int = 6

    # Pupil contour hard-rejection limits
    pupil_min_area_px: int = 40
    pupil_max_area_px: int = 6000
    pupil_min_circularity: float = 0.20
    pupil_max_axis_ratio: float = 2.8

    # Maximum absolute intensity for a valid pupil (0-255).
    # Regions brighter than this are rejected (reflections, highlights).
    pupil_max_mean_intensity: int = 80

    # Minimum contrast (pupil vs surrounding ring), in intensity units.
    pupil_min_contrast: float = 15.0

    # Hough circle fallback
    hough_dp: float = 1.2
    hough_min_dist_px: int = 20
    hough_param1: int = 50
    hough_param2: int = 15
    hough_min_radius_px: int = 5
    hough_max_radius_px: int = 35

    # Temporal outlier: frame-to-frame jump larger than this in FRAME PIXELS
    # is flagged as a potential outlier and confidence-penalised.
    max_pupil_jump_px: float = 40.0


@dataclass
class PupilScoringConfig:
    """
    Weights for the multi-signal candidate scoring function.
    All weights are applied after normalising each signal to [0, 1].
    They need not sum to 1.0 — the final score is normalised.
    """
    weight_darkness: float = 0.30       # lower mean intensity → better
    weight_circularity: float = 0.20    # closer to 1.0 → better
    weight_contrast: float = 0.20       # darker than surroundings → better
    weight_size: float = 0.10           # area close to expected size
    weight_shape: float = 0.10          # axis ratio close to 1.0
    weight_center_dist: float = 0.05    # close to ROI centre (soft prior)
    weight_temporal: float = 0.05       # close to predicted location

    # Expected pupil area as fraction of the eye ROI (used for size score)
    expected_area_fraction: float = 0.05   # ~5% of ROI


@dataclass
class TemporalConfig:
    """Per-eye temporal tracking and outlier rejection."""
    # Confidence multiplier when a jump exceeds max_pupil_jump_px
    outlier_confidence_penalty: float = 0.25
    # Frames without a valid detection before confidence decays to 0
    max_lost_frames: int = 8
    # History length for temporal prediction
    history_frames: int = 10


@dataclass
class BlinkConfig:
    # EAR below this → eye considered closed.
    # Guard: EAR must be > 0.0 to count; 0.0 means no detection, not blink.
    ear_closed_threshold: float = 0.21
    ear_consec_frames: int = 2
    min_blink_duration_ms: float = 50.0
    max_blink_duration_ms: float = 500.0
    # Rolling window (seconds) for adaptive baseline EAR calculation
    adaptive_baseline_window_sec: float = 10.0


@dataclass
class SaccadeConfig:
    # Velocity threshold in PIXELS PER SECOND using actual pupil pixel coords.
    # Typical human saccade: 300–700 deg/s; at 30 px/deg ≈ 9000–21000 px/s.
    # For a laptop webcam at 720p a conservative threshold is ~200 px/s.
    velocity_threshold_px_per_sec: float = 200.0
    min_duration_ms: float = 10.0
    max_duration_ms: float = 150.0
    min_amplitude_px: float = 8.0
    pixels_per_degree: float = 30.0


@dataclass
class FixationConfig:
    max_dispersion_px: float = 25.0
    min_duration_ms: float = 100.0
    window_size_frames: int = 10
    # Safety cap on candidate list (prevents memory leak during very long fixations)
    max_candidate_frames: int = 1800    # 60 s at 30 fps


@dataclass
class SmoothingConfig:
    # "moving_average" | "exponential" | "savgol" | "kalman"
    method: str = "kalman"
    moving_avg_window: int = 5
    exponential_alpha: float = 0.35
    savgol_window: int = 11
    savgol_polyorder: int = 3
    # Kalman: σ_a² (acceleration noise variance) — tune for responsiveness
    kalman_process_noise: float = 5.0
    # Kalman: measurement noise variance in pixel² (higher = more smoothing)
    kalman_measurement_noise: float = 20.0


@dataclass
class QualityConfig:
    """Thresholds for per-frame quality flag generation."""
    # Eye ROI mean intensity (0-255) below this → "low_light"
    low_light_threshold: int = 40
    # Eye ROI mean intensity above this → "overexposed"
    overexposed_threshold: int = 220
    # Laplacian variance on eye ROI below this → "motion_blur"
    blur_threshold: float = 25.0
    # Pupil confidence below this → "low_pupil_confidence"
    min_pupil_confidence: float = 0.35
    # Frame-to-frame gaze jump in pixels above this → "unrealistic_jump"
    unrealistic_jump_px: float = 60.0


@dataclass
class CameraDistanceConfig:
    """
    Thresholds for camera-distance quality guidance.
    No real-world distance measurement — purely relative frame metrics.
    """
    # Face bbox width as a fraction of frame width
    min_face_width_ratio: float = 0.10   # < this → too far
    max_face_width_ratio: float = 0.65   # > this → too close
    # Face bbox height as fraction of frame height
    max_face_height_ratio: float = 0.75  # > this → too close
    # Inter-eye distance in pixels (rough proxy for distance)
    min_inter_eye_distance_px: int = 35  # < this → too far
    # Eye ROI width in pixels (from EyeRegionDetector output)
    min_eye_roi_width_px: int = 50       # < this → too far
    # Hysteresis: require N consecutive frames of new status before switching
    hysteresis_frames: int = 15


@dataclass
class TaskConfig:
    """
    Configuration for structured eye-movement task protocols (v0.3).

    This covers pro-saccade, anti-saccade, gap-overlap, and smooth pursuit.
    Per-task overrides (e.g. gap duration) are also here.

    ⚠ This software is a research prototype for eye-tracking data collection.
      It does NOT diagnose, treat, predict, or screen for any medical condition.
    """
    # --- General timing (seconds) ---
    num_trials: int = 20
    fixation_duration_sec: float = 1.0
    target_duration_sec: float = 2.0
    inter_trial_interval_sec: float = 1.0
    # Max time after target onset to register a saccade response
    response_window_sec: float = 0.80

    # Random seed for trial-list generation (None = non-deterministic)
    random_seed: int = -1   # -1 means use system random

    # --- Task-level saccade detection ---
    saccade_velocity_threshold_px_per_sec: float = 300.0
    # Minimum frames below threshold before onset is eligible
    saccade_min_below_frames: int = 3

    # --- Stimulus geometry (normalized [0,1] or pixels) ---
    target_eccentricity_ratio: float = 0.35   # fraction of half screen width
    target_size_px: int = 18
    fixation_size_px: int = 10
    fixation_x: float = 0.5   # normalized screen position
    fixation_y: float = 0.5

    # --- Gap / overlap specific ---
    gap_duration_sec: float = 0.20
    overlap_extra_sec: float = 0.20   # how long fixation overlaps with target

    # --- Smooth pursuit ---
    pursuit_pattern: str = "horizontal"    # horizontal | vertical | circular | figure8
    pursuit_speed_cycles_per_sec: float = 0.3
    pursuit_amplitude_ratio: float = 0.40  # fraction of half-screen width/height
    pursuit_num_cycles: int = 8

    # --- Display ---
    screen_width: int = 1280
    screen_height: int = 720
    fullscreen: bool = False
    bg_color: Tuple[int, int, int] = (30, 30, 30)          # BGR dark gray
    target_color: Tuple[int, int, int] = (255, 255, 255)   # white
    fixation_color: Tuple[int, int, int] = (255, 255, 255) # white
    error_highlight_color: Tuple[int, int, int] = (50, 50, 220)  # red for errors
    # PIP camera preview fraction of screen width
    pip_width_ratio: float = 0.22


@dataclass
class WebCaptureConfig:
    """
    Settings for the in-browser web task mode (v0.5), where the browser renders
    the stimulus and streams frames to the backend for tracking.

    The FPS / quality / resolution values are advisory defaults the frontend
    reads via /api/web-config; the browser does the actual capturing.
    """
    upload_fps: int = 15                 # WEB_FRAME_UPLOAD_FPS
    jpeg_quality: int = 85               # WEB_FRAME_JPEG_QUALITY (0-100)
    max_width: int = 960                 # WEB_FRAME_MAX_WIDTH
    max_height: int = 720                # WEB_FRAME_MAX_HEIGHT
    backend_timeout_ms: int = 4000       # WEB_BACKEND_TIMEOUT_MS
    # Horizontal gaze displacement (normalized 0-1) that counts as a saccadic
    # response when reconstructing trials from streamed frames.
    response_position_threshold: float = 0.06
    # Privacy: never persist raw frames/eye crops unless explicitly enabled.
    save_debug_crops: bool = False

    # ---- Pre-task stabilization gate (frontend reads these via /web-config) ----
    # Require a short stable tracking window before the countdown can begin.
    stabilization_window_ms: int = 1500   # length of the rolling stability window
    stabilization_min_usable_ratio: float = 0.80  # ≥80% usable frames in window
    stabilization_min_samples: int = 8    # need at least this many frames first

    # ---- Trial-quality grace (backend trial_quality engine) ----
    # A trial is judged on its RESPONSE WINDOW, with tolerance for brief loss.
    usable_confidence_threshold: float = 0.40   # per-frame "usable" floor
    trial_clear_min_usable_percent: float = 70.0
    trial_response_window_min_percent: float = 60.0
    trial_bad_max_usable_percent: float = 40.0
    # A face gap no longer than this is a bridgeable "short dropout", not a loss.
    short_dropout_max_ms: int = 200
    # Frames within this window after target onset are the "onset guard".
    target_onset_guard_ms: int = 150
    # Treat a sustained in-task face loss longer than this as an interruption.
    task_face_loss_warn_ms: int = 1000


@dataclass
class DataConfig:
    output_dir: str = "sessions"
    db_filename: str = "eye_tracking.db"
    auto_create_output_dir: bool = True


@dataclass
class DebugConfig:
    """
    When enabled, saves intermediate detection images to disk.
    Useful for diagnosing why the detector fails.
    """
    enabled: bool = False
    save_eye_rois: bool = True
    save_threshold_images: bool = True
    save_candidate_overlays: bool = True
    output_dir: str = "sessions/debug"
    # Only save debug frames every N frames (0 = every frame)
    save_every_n_frames: int = 5


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
    show_quality_flags: bool = True

    # BGR colours
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
    pupil_scoring: PupilScoringConfig = field(default_factory=PupilScoringConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    blink: BlinkConfig = field(default_factory=BlinkConfig)
    saccade: SaccadeConfig = field(default_factory=SaccadeConfig)
    fixation: FixationConfig = field(default_factory=FixationConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    data: DataConfig = field(default_factory=DataConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    camera_distance: CameraDistanceConfig = field(default_factory=CameraDistanceConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    web_capture: WebCaptureConfig = field(default_factory=WebCaptureConfig)
    log_level: str = "INFO"
    enable_smoothing: bool = True
    enable_calibration: bool = False


# Module-level singleton
CONFIG = AppConfig()
