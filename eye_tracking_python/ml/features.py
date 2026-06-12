"""
Feature extraction from tracker export files.

Every function reads the SAME CSV columns the real tracker writes, so this code
runs unchanged on real data. All functions are robust to missing/empty files and
return NaN for any feature they cannot compute (imputed later, inside the CV fold).

Each feature's PD rationale and webcam-plausibility tag live in ``schema.FEATURE_INFO``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.schema import FEATURE_COLUMNS

NAN = float("nan")


def _read_csv(path: Path) -> pd.DataFrame | None:
    """Read a CSV, returning None if missing or empty."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return None
    return df if len(df) else None


# ---------------------------------------------------------------------------
# Blink features  (from <sid>_blinks.csv + <sid>_frames.csv)
# ---------------------------------------------------------------------------

def blink_features(rest_sid: str, data_dir: Path) -> dict:
    """Blink rate (per minute) and inter-blink-interval CV.

    PD: blink rate tends to be LOWER (dopaminergic). This is the most
    webcam-reliable signal here.
    """
    blinks = _read_csv(data_dir / f"{rest_sid}_blinks.csv")
    frames = _read_csv(data_dir / f"{rest_sid}_frames.csv")

    # Session duration from frames (fall back to blink span if needed).
    duration_min = NAN
    if frames is not None and "timestamp_sec" in frames:
        duration_min = (frames["timestamp_sec"].max() - frames["timestamp_sec"].min()) / 60.0
    elif blinks is not None and "end_timestamp_sec" in blinks:
        duration_min = blinks["end_timestamp_sec"].max() / 60.0

    if blinks is None:
        return {"blink_rate_per_min": NAN, "blink_interval_cv": NAN}

    n_blinks = len(blinks)
    rate = n_blinks / duration_min if duration_min and duration_min > 0 else NAN

    cv = NAN
    if n_blinks >= 3 and "start_timestamp_sec" in blinks:
        onsets = np.sort(blinks["start_timestamp_sec"].to_numpy())
        intervals = np.diff(onsets)
        if intervals.size and intervals.mean() > 0:
            cv = float(intervals.std() / intervals.mean())
    return {"blink_rate_per_min": float(rate) if rate == rate else NAN,
            "blink_interval_cv": cv}


# ---------------------------------------------------------------------------
# Saccade-task features  (from <sid>_trials.csv)
# ---------------------------------------------------------------------------

def antisaccade_features(sid: str, data_dir: Path) -> dict:
    """Antisaccade error rate, correct-response latency, and correction rate.

    PD: error rate HIGHER (inhibition deficit), latency longer. The error rate
    is a behavioural outcome and is the strongest webcam-accessible signal.
    """
    df = _read_csv(data_dir / f"{sid}_trials.csv")
    if df is None:
        return {"antisacc_error_rate": NAN, "antisacc_latency_ms_median": NAN,
                "antisacc_correction_rate": NAN}

    error_rate = float(df["error_saccade_detected"].mean()) if "error_saccade_detected" in df else NAN

    latency = NAN
    if "direction_correct" in df and "response_latency_ms" in df:
        correct = df[(df["direction_correct"] == 1) & (df["response_latency_ms"] > 0)]
        if len(correct):
            latency = float(correct["response_latency_ms"].median())

    corr_rate = NAN
    if "error_saccade_detected" in df and "correction_made" in df:
        errs = df[df["error_saccade_detected"] == 1]
        if len(errs):
            corr_rate = float(errs["correction_made"].mean())

    return {"antisacc_error_rate": error_rate,
            "antisacc_latency_ms_median": latency,
            "antisacc_correction_rate": corr_rate}


def prosaccade_features(sid: str, data_dir: Path) -> dict:
    """Prosaccade latency (median + IQR) and error rate.

    PD: latency modestly longer and more variable.
    """
    df = _read_csv(data_dir / f"{sid}_trials.csv")
    if df is None:
        return {"prosacc_latency_ms_median": NAN, "prosacc_latency_ms_iqr": NAN,
                "prosacc_error_rate": NAN}

    med = iqr = NAN
    if "direction_correct" in df and "response_latency_ms" in df:
        correct = df[(df["direction_correct"] == 1) & (df["response_latency_ms"] > 0)]
        if len(correct):
            lat = correct["response_latency_ms"]
            med = float(lat.median())
            iqr = float(lat.quantile(0.75) - lat.quantile(0.25))
    err = float((df["direction_correct"] == 0).mean()) if "direction_correct" in df else NAN
    return {"prosacc_latency_ms_median": med, "prosacc_latency_ms_iqr": iqr,
            "prosacc_error_rate": err}


def pursuit_features(sid: str, data_dir: Path) -> dict:
    """Smooth-pursuit gain, catch-up saccade rate, and on-target ratio.

    PD: gain LOWER, more catch-up saccades, less time on target ('cogwheeling').
    """
    df = _read_csv(data_dir / f"{sid}_trials.csv")
    if df is None:
        return {"pursuit_gain_mean": NAN, "pursuit_catchup_rate": NAN,
                "pursuit_on_target_ratio": NAN}
    gain = float(df["mean_pursuit_gain"].mean()) if "mean_pursuit_gain" in df else NAN
    catchup = float(df["catch_up_saccade_count"].mean()) if "catch_up_saccade_count" in df else NAN
    on_target = float(df["time_on_target_ratio"].mean()) if "time_on_target_ratio" in df else NAN
    return {"pursuit_gain_mean": gain, "pursuit_catchup_rate": catchup,
            "pursuit_on_target_ratio": on_target}


def fixation_features(rest_sid: str, data_dir: Path) -> dict:
    """Median fixation dispersion (instability).

    PD: more drift / square-wave jerks. NOTE: only gross instability is above
    webcam noise; treat this as a weak, exploratory feature.
    """
    df = _read_csv(data_dir / f"{rest_sid}_fixations.csv")
    if df is None or "dispersion_px" not in df:
        return {"fixation_dispersion_median": NAN}
    return {"fixation_dispersion_median": float(df["dispersion_px"].median())}


# ---------------------------------------------------------------------------
# One feature vector per "battery" (one assessment of one subject)
# ---------------------------------------------------------------------------

def extract_battery_features(manifest_row: dict, data_dir: str | Path) -> dict:
    """Combine all task features for a single battery into one ordered dict.

    ``manifest_row`` is one row of manifest.csv (see schema.MANIFEST_FIELDS).
    Returns features in ``FEATURE_COLUMNS`` order; missing tasks -> NaN.
    """
    d = Path(data_dir)
    feats: dict = {}
    feats.update(blink_features(str(manifest_row["rest_sid"]), d))
    feats.update(fixation_features(str(manifest_row["rest_sid"]), d))
    feats.update(antisaccade_features(str(manifest_row["antisacc_sid"]), d))
    feats.update(prosaccade_features(str(manifest_row["prosacc_sid"]), d))
    feats.update(pursuit_features(str(manifest_row["pursuit_sid"]), d))
    # Return strictly in model order, filling anything absent with NaN.
    return {col: feats.get(col, NAN) for col in FEATURE_COLUMNS}
