"""
Tests for backend.services.result_parser using a synthetic session fixture
(so the suite is deterministic and does not depend on real recordings).
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


def _write_prosaccade_session(d: Path, sid: str = "testpro1") -> str:
    analysis = {
        "task_type": "prosaccade",
        "total_trials": 10,
        "response_count": 8,
        "response_rate": 0.8,
        "correct_count": 7,
        "direction_accuracy": 0.875,
        "mean_latency_ms": 265.0,
        "sd_latency_ms": 30.0,
        "min_latency_ms": 210.0,
        "max_latency_ms": 320.0,
        "mean_peak_velocity_px_per_sec": 450.0,
        "left_accuracy": 0.8,
        "right_accuracy": 0.95,
        "disclaimer": DISCLAIMER,
    }
    (d / f"{sid}_task_metadata.json").write_text(json.dumps({
        "session_id": sid,
        "task_id": "tid1",
        "task_type": "prosaccade",
        "subject_id": "p1",
        "software_version": "0.3.0",
        "timestamp_start": 1700000000.0,
        "timestamp_end": 1700000030.0,
        "duration_sec": 30.0,
        "num_completed_trials": 10,
        "task_config": {},
        "analysis": analysis,
        "disclaimer": DISCLAIMER,
    }))
    (d / f"{sid}_metadata.json").write_text(json.dumps({
        "session_id": sid,
        "summary": {
            "total_frames": 900,
            "good_frames": 810,
            "good_frame_ratio": 0.9,
            "blink_count": 5,
        },
    }))
    # tiny frames.csv to exercise the confidence fallback
    (d / f"{sid}_frames.csv").write_text(
        "frame_number,face_detected,confidence_score,frame_quality\n"
        "0,1,0.90,good\n1,1,0.80,good\n2,0,0.0,bad\n"
    )
    (d / f"{sid}_trials.csv").write_text("session_id,trial_number\n" + f"{sid},1\n")
    return sid


class TestQualityLabel:
    def test_excellent(self):
        assert result_parser.quality_label(92) == "Excellent"

    def test_good(self):
        assert result_parser.quality_label(75) == "Good"

    def test_okay(self):
        assert result_parser.quality_label(55) == "Okay"

    def test_needs_setup(self):
        assert result_parser.quality_label(30) == "Needs better camera setup"

    def test_none_defaults_okay(self):
        assert result_parser.quality_label(None) == "Okay"


class TestFriendlyName:
    def test_all_known(self):
        assert result_parser.friendly_name("prosaccade") == "Look Toward the Dot"
        assert result_parser.friendly_name("antisaccade") == "Look Away from the Dot"
        assert result_parser.friendly_name("gap_overlap") == "Quick Reaction Dot Task"
        assert result_parser.friendly_name("smooth_pursuit") == "Follow the Moving Dot"


class TestParseSession:
    def test_parse_prosaccade(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path)
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)

        assert s["session_id"] == sid
        assert s["technical_task_name"] == "prosaccade"
        assert s["activity_name"] == "Look Toward the Dot"
        assert s["status"] == "completed"
        assert s["tracking_quality_label"] == "Excellent"  # 90%
        assert s["usable_data_percent"] == 90.0
        assert s["blink_count"] == 5
        assert s["rounds_completed"] == 10
        assert s["average_response_time_ms"] == 265.0
        assert s["disclaimer"] == DISCLAIMER

    def test_task_metrics_shape(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path)
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        m = s["task_metrics"]
        assert m["fastest_response_ms"] == 210.0
        assert m["successful_clear_rounds"] == 7
        assert m["unclear_rounds"] == 2  # 10 total - 8 responded
        assert m["direction_accuracy_percent"] == 87.5

    def test_average_confidence_from_frames(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path)
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        # mean of face-detected rows (0.90, 0.80) = 0.85
        assert s["average_confidence"] == 0.85

    def test_exports_only_existing(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path)
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        assert "task_metadata" in s["exports"]
        assert "frames" in s["exports"]
        assert "saccades" not in s["exports"]  # not written

    def test_recommendations_present_and_clean(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path)
        s = result_parser.parse_session(sid, sessions_dir=tmp_path)
        assert len(s["recommendations"]) >= 1
        joined = " ".join(s["recommendations"]).lower()
        for banned in ("diagnos", "parkinson", "risk score"):
            assert banned not in joined

    def test_missing_session_raises(self, tmp_path):
        with pytest.raises(result_parser.SessionNotFound):
            result_parser.parse_session("nope", sessions_dir=tmp_path)

    def test_find_latest_completed(self, tmp_path):
        sid = _write_prosaccade_session(tmp_path, sid="latest01")
        found = result_parser.find_latest_completed(sessions_dir=tmp_path)
        assert found == sid
