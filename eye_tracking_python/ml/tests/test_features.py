"""Feature extractors compute the right numbers from tracker-format files."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from ml.features import (
    antisaccade_features,
    blink_features,
    extract_battery_features,
    prosaccade_features,
    pursuit_features,
)
from ml.schema import FEATURE_COLUMNS


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def test_antisaccade_error_rate_and_latency(tmp_path: Path):
    sid = "S0_anti"
    rows = [
        # 2 error trials, 2 clean trials -> error rate 0.5
        {"error_saccade_detected": 1, "direction_correct": 0, "response_latency_ms": 200, "correction_made": 0},
        {"error_saccade_detected": 1, "direction_correct": 1, "response_latency_ms": 300, "correction_made": 1},
        {"error_saccade_detected": 0, "direction_correct": 1, "response_latency_ms": 320, "correction_made": 0},
        {"error_saccade_detected": 0, "direction_correct": 1, "response_latency_ms": 280, "correction_made": 0},
    ]
    fields = ["error_saccade_detected", "direction_correct", "response_latency_ms", "correction_made"]
    _write(tmp_path / f"{sid}_trials.csv", fields, rows)

    f = antisaccade_features(sid, tmp_path)
    assert f["antisacc_error_rate"] == 0.5
    # median latency over direction_correct trials (300, 320, 280) -> 300
    assert f["antisacc_latency_ms_median"] == 300
    # correction rate among the 2 error trials -> 1 corrected / 2 = 0.5
    assert f["antisacc_correction_rate"] == 0.5


def test_prosaccade_latency_and_error(tmp_path: Path):
    sid = "S0_pro"
    rows = [
        {"direction_correct": 1, "response_latency_ms": 200},
        {"direction_correct": 1, "response_latency_ms": 240},
        {"direction_correct": 0, "response_latency_ms": 150},  # error
        {"direction_correct": 1, "response_latency_ms": 220},
    ]
    _write(tmp_path / f"{sid}_trials.csv", ["direction_correct", "response_latency_ms"], rows)
    f = prosaccade_features(sid, tmp_path)
    assert f["prosacc_error_rate"] == 0.25
    assert f["prosacc_latency_ms_median"] == 220  # median of {200,240,220}


def test_pursuit_gain(tmp_path: Path):
    sid = "S0_pur"
    rows = [
        {"mean_pursuit_gain": 0.8, "catch_up_saccade_count": 2, "time_on_target_ratio": 0.7},
        {"mean_pursuit_gain": 0.6, "catch_up_saccade_count": 4, "time_on_target_ratio": 0.5},
    ]
    _write(tmp_path / f"{sid}_trials.csv",
           ["mean_pursuit_gain", "catch_up_saccade_count", "time_on_target_ratio"], rows)
    f = pursuit_features(sid, tmp_path)
    assert abs(f["pursuit_gain_mean"] - 0.7) < 1e-9
    assert f["pursuit_catchup_rate"] == 3


def test_blink_rate(tmp_path: Path):
    sid = "S0_rest"
    # 60-second session via frames, 12 blinks -> 12 per minute
    frames = [{"session_id": sid, "frame_number": i, "timestamp_sec": i / 30.0,
               "blink_detected": 0} for i in range(int(60 * 30))]
    _write(tmp_path / f"{sid}_frames.csv",
           ["session_id", "frame_number", "timestamp_sec", "blink_detected"], frames)
    blinks = [{"session_id": sid, "event_id": f"b{i}", "start_timestamp_sec": i * 5.0,
               "end_timestamp_sec": i * 5.0 + 0.1, "duration_ms": 100,
               "affected_eye": "both", "confidence": 0.9} for i in range(12)]
    _write(tmp_path / f"{sid}_blinks.csv",
           ["session_id", "event_id", "start_timestamp_sec", "end_timestamp_sec",
            "duration_ms", "affected_eye", "confidence"], blinks)

    f = blink_features(sid, tmp_path)
    # 12 blinks over ~59.97 min-seconds -> ~12.0 per minute
    assert abs(f["blink_rate_per_min"] - 12.0) < 0.1


def test_missing_files_return_nan(tmp_path: Path):
    f = antisaccade_features("does_not_exist", tmp_path)
    assert all(math.isnan(v) for v in f.values())


def test_extract_battery_returns_all_features_in_order(tmp_path: Path):
    row = {"rest_sid": "x_rest", "antisacc_sid": "x_anti",
           "prosacc_sid": "x_pro", "pursuit_sid": "x_pur"}
    feats = extract_battery_features(row, tmp_path)  # nothing on disk -> all NaN
    assert list(feats.keys()) == FEATURE_COLUMNS
    assert all(math.isnan(v) for v in feats.values())
