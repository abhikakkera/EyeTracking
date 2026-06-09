"""
Tests for backend.services.result_parser (v0.5 — usable% / quality / null fixes).

Synthetic sessions only, so the suite is deterministic.

Covers the bug-report scenarios:
  A. 12 trials, frames uploaded, no valid gaze   → 0% usable, 0 valid, "Needs better camera setup", null RTs
  B. 12 trials, 10 valid responses               → 10 valid, RT computed, label not contradicted
  C. Missing response times                      → null, not 0
  E. Quality badge cannot be Excellent if valid_trials == 0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.paths import DISCLAIMER
from backend.services import result_parser

_FRAME_HEADER = (
    "frame_number,face_detected,left_eye_detected,right_eye_detected,"
    "left_pupil_detected,right_pupil_detected,blink_detected,"
    "frame_quality,confidence_score"
)


def _frame(i: int, usable: bool) -> str:
    if usable:
        return f"{i},1,1,1,1,1,0,good,0.9"
    # face + eye visible but no pupil/gaze and low confidence → NOT usable
    return f"{i},1,1,1,0,0,0,questionable,0.2"


def _write_session(
    d: Path,
    sid: str,
    task_type: str,
    analysis: dict,
    *,
    usable_frames: int,
    total_frames: int,
    responded_trials: int,
    total_trials: int,
    blink_count: int = 4,
) -> str:
    (d / f"{sid}_task_metadata.json").write_text(json.dumps({
        "session_id": sid, "task_id": "tid", "task_type": task_type,
        "subject_id": "p1", "software_version": "0.5.0",
        "timestamp_start": 1700000000.0, "timestamp_end": 1700000030.0,
        "duration_sec": 30.0, "num_completed_trials": total_trials,
        "task_config": {}, "analysis": analysis, "disclaimer": DISCLAIMER,
    }))
    (d / f"{sid}_metadata.json").write_text(json.dumps({
        "session_id": sid,
        "summary": {"total_frames": total_frames,
                    "good_frames": usable_frames,
                    "good_frame_ratio": round(usable_frames / max(total_frames, 1), 3),
                    "blink_count": blink_count},
    }))
    rows = [_FRAME_HEADER]
    for i in range(total_frames):
        rows.append(_frame(i, usable=i < usable_frames))
    (d / f"{sid}_frames.csv").write_text("\n".join(rows) + "\n")

    trial_rows = ["trial_number,response_detected"]
    for i in range(total_trials):
        trial_rows.append(f"{i + 1},{1 if i < responded_trials else 0}")
    (d / f"{sid}_trials.csv").write_text("\n".join(trial_rows) + "\n")
    return sid


def _prosaccade_analysis(*, total: int, responded: int,
                         mean_lat=None, min_lat=None) -> dict:
    return {
        "task_type": "prosaccade",
        "total_trials": total,
        "response_count": responded,
        "response_rate": round(responded / total, 3) if total else None,
        "correct_count": responded,
        "direction_accuracy": round(responded / responded, 3) if responded else None,
        "mean_latency_ms": mean_lat,
        "sd_latency_ms": None,
        "min_latency_ms": min_lat,
        "max_latency_ms": None,
        "mean_peak_velocity_px_per_sec": 420.0 if responded else None,
        "left_accuracy": None,
        "right_accuracy": None,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# quality_label (new 4-arg signature)
# ---------------------------------------------------------------------------

class TestQualityLabel:
    def test_excellent(self):
        assert result_parser.quality_label(92, 0.9, 9, 10) == "Excellent"

    def test_good(self):
        assert result_parser.quality_label(78, 0.74, 7, 10) == "Good"

    def test_okay(self):
        assert result_parser.quality_label(65, 0.6, 5, 10) == "Okay"

    def test_low_usable_needs_setup(self):
        assert result_parser.quality_label(40, 0.9, 8, 10) == "Needs better camera setup"

    def test_zero_valid_trials_never_excellent(self):
        # Even with perfect frames, no valid trials → cannot be Excellent.
        assert result_parser.quality_label(100, 0.95, 0, 12) == "Needs better camera setup"

    def test_missing_confidence_blocks_excellent(self):
        # No confidence measured → not Excellent/Good.
        assert result_parser.quality_label(95, None, 9, 10) != "Excellent"

    def test_all_none_needs_setup(self):
        assert result_parser.quality_label(None, None, 0, 0) == "Needs better camera setup"


# ---------------------------------------------------------------------------
# Scenario A — frames uploaded, no valid gaze
# ---------------------------------------------------------------------------

class TestScenarioA_NoGaze:
    def test_no_gaze_session(self, tmp_path):
        sid = _write_session(
            tmp_path, "noGaze01", "prosaccade",
            _prosaccade_analysis(total=12, responded=0),
            usable_frames=0, total_frames=60,
            responded_trials=0, total_trials=12,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)

        assert s["usable_data_percent"] == 0.0
        assert s["diagnostics"]["valid_trials"] == 0
        assert s["diagnostics"]["unclear_trials"] == 12
        assert s["tracking_quality_label"] == "Needs better camera setup"
        assert s["average_response_time_ms"] is None
        assert s["task_metrics"]["average_response_time_ms"] is None
        assert s["task_metrics"]["fastest_response_ms"] is None
        assert s["notes"]  # "No clear eye-movement responses..."


# ---------------------------------------------------------------------------
# Scenario B — valid responses in 10 of 12
# ---------------------------------------------------------------------------

class TestScenarioB_ValidResponses:
    def test_valid_session(self, tmp_path):
        sid = _write_session(
            tmp_path, "valid01", "prosaccade",
            _prosaccade_analysis(total=12, responded=10, mean_lat=284.0, min_lat=205.0),
            usable_frames=100, total_frames=100,
            responded_trials=10, total_trials=12,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)

        assert s["diagnostics"]["valid_trials"] == 10
        assert s["diagnostics"]["unclear_trials"] == 2
        assert s["average_response_time_ms"] == 284.0
        assert s["usable_data_percent"] == 100.0
        # Quality must NOT be contradicted by the trial summary.
        assert s["tracking_quality_label"] in ("Excellent", "Good")
        assert s["tracking_quality_label"] != "Needs better camera setup"


# ---------------------------------------------------------------------------
# Scenario C — missing response times are null, not 0
# ---------------------------------------------------------------------------

class TestScenarioC_NullNotZero:
    def test_missing_rt_is_null(self, tmp_path):
        sid = _write_session(
            tmp_path, "nullrt01", "prosaccade",
            _prosaccade_analysis(total=12, responded=0),
            usable_frames=10, total_frames=60,
            responded_trials=0, total_trials=12,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        assert s["average_response_time_ms"] is None
        assert s["task_metrics"]["fastest_response_ms"] is None
        # A real measured percent (0 responded of 12) is allowed to be 0.0.
        assert s["task_metrics"]["rounds_with_response_percent"] == 0.0


# ---------------------------------------------------------------------------
# Scenario E — Excellent impossible with 0 valid trials even if frames perfect
# ---------------------------------------------------------------------------

class TestScenarioE_BadgeGuard:
    def test_perfect_frames_zero_responses(self, tmp_path):
        sid = _write_session(
            tmp_path, "guard01", "prosaccade",
            _prosaccade_analysis(total=12, responded=0),
            usable_frames=100, total_frames=100,   # 100% usable frames…
            responded_trials=0, total_trials=12,    # …but no valid trials
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        assert s["usable_data_percent"] == 100.0
        assert s["tracking_quality_label"] == "Needs better camera setup"
        assert s["tracking_quality_label"] != "Excellent"


# ---------------------------------------------------------------------------
# Task-appropriate fields
# ---------------------------------------------------------------------------

class TestTaskAppropriateFields:
    def test_prosaccade_has_no_direction_accuracy(self, tmp_path):
        sid = _write_session(
            tmp_path, "fields01", "prosaccade",
            _prosaccade_analysis(total=10, responded=8, mean_lat=260.0, min_lat=200.0),
            usable_frames=90, total_frames=100,
            responded_trials=8, total_trials=10,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        m = s["task_metrics"]
        # Pro-saccade must NOT show anti-saccade-style accuracy fields.
        assert "direction_accuracy_percent" not in m
        assert "left_accuracy_percent" not in m
        assert "right_accuracy_percent" not in m
        # It SHOULD show its own fields.
        assert "average_response_time_ms" in m
        assert "fastest_response_ms" in m
        assert "successful_clear_rounds" in m
        assert "rounds_with_response_percent" in m


# ---------------------------------------------------------------------------
# Diagnostics object
# ---------------------------------------------------------------------------

class TestDiagnostics:
    def test_diagnostics_keys(self, tmp_path):
        sid = _write_session(
            tmp_path, "diag01", "prosaccade",
            _prosaccade_analysis(total=10, responded=6, mean_lat=300.0, min_lat=240.0),
            usable_frames=70, total_frames=100,
            responded_trials=6, total_trials=10,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        d = s["diagnostics"]
        for key in (
            "total_frames_received", "frames_with_face_detected",
            "frames_with_eye_detected", "frames_with_pupil_or_gaze_detected",
            "usable_eye_tracking_frames", "total_trials", "valid_trials",
            "unclear_trials", "average_confidence", "missing_gaze_reason_counts",
        ):
            assert key in d
        assert d["usable_eye_tracking_frames"] == 70
        assert d["total_frames_received"] == 100

    def test_extra_diagnostics_merged(self, tmp_path):
        sid = _write_session(
            tmp_path, "diag02", "prosaccade",
            _prosaccade_analysis(total=10, responded=6, mean_lat=300.0, min_lat=240.0),
            usable_frames=70, total_frames=100,
            responded_trials=6, total_trials=10,
        )
        s = result_parser.parse_session(
            sid, sessions_dir=tmp_path,
            extra_diagnostics={"task_events_received": 42, "target_onset_events_received": 10},
        )
        assert s["diagnostics"]["task_events_received"] == 42
        assert s["diagnostics"]["target_onset_events_received"] == 10


# ---------------------------------------------------------------------------
# Misc (kept from before)
# ---------------------------------------------------------------------------

class TestMisc:
    def test_friendly_names(self):
        assert result_parser.friendly_name("prosaccade") == "Look Toward the Dot"
        assert result_parser.friendly_name("smooth_pursuit") == "Follow the Moving Dot"

    def test_missing_session_raises(self, tmp_path):
        with pytest.raises(result_parser.SessionNotFound):
            result_parser.parse_session("nope", sessions_dir=tmp_path)

    def test_recommendations_clean(self, tmp_path):
        sid = _write_session(
            tmp_path, "rec01", "prosaccade",
            _prosaccade_analysis(total=10, responded=0),
            usable_frames=0, total_frames=50,
            responded_trials=0, total_trials=10,
        )
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        joined = " ".join(s["recommendations"]).lower()
        for banned in ("diagnos", "parkinson", "risk score"):
            assert banned not in joined
