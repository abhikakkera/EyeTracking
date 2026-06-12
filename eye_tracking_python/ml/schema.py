"""
Single source of truth for column names and the feature catalogue.

The CSV column names here MUST match what the tracker writes
(see ``src/data/export_csv.py`` and ``src/data/export_task.py``).
Keeping them in one place means the simulator writes real-format files and the
feature extractors read them with the same constants.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Tracker export column names (subset this pipeline consumes)
# ---------------------------------------------------------------------------

# <sid>_blinks.csv
BLINK_FIELDS = [
    "session_id", "event_id",
    "start_timestamp_sec", "end_timestamp_sec",
    "duration_ms", "affected_eye", "confidence",
]

# <sid>_fixations.csv
FIXATION_FIELDS = [
    "session_id", "event_id",
    "start_timestamp_sec", "end_timestamp_sec",
    "duration_ms", "center_x", "center_y", "dispersion_px",
    "num_frames", "confidence",
]

# <sid>_frames.csv (only the columns we actually use here)
FRAME_FIELDS = [
    "session_id", "frame_number", "timestamp_sec", "blink_detected",
    "left_ear", "right_ear", "gaze_x", "gaze_y",
]

# <sid>_trials.csv for pro/anti-saccade tasks
SACCADE_TRIAL_FIELDS = [
    "session_id", "task_id", "trial_id", "trial_number", "condition",
    "fixation_onset_sec", "target_onset_sec", "trial_end_sec",
    "response_detected", "response_onset_sec", "response_latency_ms",
    "response_direction", "response_velocity_px_per_sec", "response_amplitude_px",
    "target_x", "target_y", "target_direction",
    "direction_correct", "error_saccade_detected", "correction_made",
]

# <sid>_trials.csv for smooth-pursuit task
PURSUIT_TRIAL_FIELDS = [
    "session_id", "task_id", "trial_id", "trial_number", "cycle_number",
    "target_onset_sec", "trial_end_sec",
    "target_peak_velocity_px_per_sec",
    "mean_pursuit_gain", "mean_position_error_px",
    "time_on_target_ratio", "catch_up_saccade_count",
]


# ---------------------------------------------------------------------------
# Feature catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureInfo:
    name: str
    pd_direction: str       # how the value tends to move in PD (group-level)
    plausible: str          # webcam plausibility: "yes" | "coarse" | "no"
    rationale: str


# Order here defines the model's feature-vector order.
FEATURE_INFO: list[FeatureInfo] = [
    FeatureInfo(
        "blink_rate_per_min", "lower", "yes",
        "Reduced spontaneous blink rate is a robust, dopamine-linked PD sign and "
        "is one of the few signals a 30 FPS webcam can measure well.",
    ),
    FeatureInfo(
        "blink_interval_cv", "higher", "coarse",
        "Variability of inter-blink intervals; more exploratory than the rate itself.",
    ),
    FeatureInfo(
        "antisacc_error_rate", "higher", "yes",
        "Antisaccade errors (looking TOWARD the target) reflect an inhibition "
        "deficit. It is a behavioural outcome — a large, slow, wrong-direction "
        "movement — so a webcam can detect it. Arguably the strongest webcam signal.",
    ),
    FeatureInfo(
        "antisacc_latency_ms_median", "higher", "coarse",
        "Latency of the correct volitional saccade; timing is measurable at ~33 ms "
        "resolution (30 FPS), so direction is plausible but precision is limited.",
    ),
    FeatureInfo(
        "antisacc_correction_rate", "lower", "coarse",
        "Fraction of error saccades that get corrected; exploratory.",
    ),
    FeatureInfo(
        "prosacc_latency_ms_median", "higher", "coarse",
        "Visually-guided saccade latency; modestly prolonged in PD, coarse on webcam.",
    ),
    FeatureInfo(
        "prosacc_latency_ms_iqr", "higher", "coarse",
        "Spread of prosaccade latencies; intra-individual variability tends to rise.",
    ),
    FeatureInfo(
        "prosacc_error_rate", "higher", "coarse",
        "Wrong-direction prosaccades; usually low, weak signal.",
    ),
    FeatureInfo(
        "pursuit_gain_mean", "lower", "coarse",
        "Smooth-pursuit gain (eye velocity / target velocity) drops in PD "
        "('cogwheel' pursuit). Pursuit is slow, so a webcam can approximate it.",
    ),
    FeatureInfo(
        "pursuit_catchup_rate", "higher", "coarse",
        "Catch-up saccades per cycle increase when pursuit gain falls.",
    ),
    FeatureInfo(
        "pursuit_on_target_ratio", "lower", "coarse",
        "Fraction of the cycle the eye stays near the target.",
    ),
    FeatureInfo(
        "fixation_dispersion_median", "higher", "coarse",
        "Fixation instability (drift / square-wave jerks). Only gross instability "
        "is above webcam noise; small square-wave jerks are not measurable.",
    ),
]

FEATURE_COLUMNS: list[str] = [f.name for f in FEATURE_INFO]

# Metadata columns carried alongside features (NOT fed to the model as inputs,
# except where a covariate is explicitly added).
META_COLUMNS = ["battery_id", "subject_id", "label", "age", "sex", "run"]

# Manifest (participant log) — links a single assessment ("battery") of one
# subject to that subject's task session files. Labels live HERE, with the
# subject, never inside raw tracker output.
MANIFEST_FIELDS = [
    "battery_id", "subject_id", "label", "age", "sex", "run",
    "antisacc_sid", "prosacc_sid", "pursuit_sid", "rest_sid",
]

# Features that are NOT reliably measurable on a webcam and are therefore
# intentionally EXCLUDED from the model. Listed so reviewers can see the choice
# was deliberate, not an oversight.
EXCLUDED_NOT_WEBCAM_PLAUSIBLE = {
    "saccade_peak_velocity": "A 30-80 ms saccade gives 1-3 samples at 30 FPS — "
                             "peak velocity cannot be measured.",
    "microsaccades": "Amplitude < 1 deg, ~20 ms — below webcam spatial AND "
                     "temporal resolution; anything labelled 'microsaccade' is noise.",
    "ocular_tremor": "Ocular microtremor is arc-minutes at 40-100 Hz — not "
                     "measurable by any webcam.",
    "pupil_diameter_mm": "Webcam pupil size is in pixels, confounded by distance "
                         "and lighting; no mm without IR / calibration.",
}
