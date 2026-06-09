"""
Tests that task analysis returns None (not 0) when there is nothing to measure.
This is the source-level half of the "0 ms / 0%" bug fix.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.tasks.task_analysis import analyze_prosaccade, analyze_smooth_pursuit
from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    SaccadeTrialRecord,
)


def _sacc(resp: bool, correct: bool = False, lat: float = 0.0,
          tdir: SaccadeDirection = SaccadeDirection.LEFT) -> SaccadeTrialRecord:
    return SaccadeTrialRecord(
        session_id="s", task_id="t", trial_number=1,
        target_direction=tdir, response_detected=resp,
        direction_correct=correct, response_latency_ms=lat,
        response_velocity_px_per_sec=300.0 if resp else 0.0,
    )


class TestProsaccadeNull:
    def test_no_responses_returns_none(self):
        a = analyze_prosaccade([_sacc(False) for _ in range(12)])
        assert a["total_trials"] == 12
        assert a["response_count"] == 0
        # No responses → these are None, NOT 0.
        assert a["mean_latency_ms"] is None
        assert a["min_latency_ms"] is None
        assert a["max_latency_ms"] is None
        assert a["direction_accuracy"] is None
        assert a["mean_peak_velocity_px_per_sec"] is None
        # A real measured rate of 0/12 is allowed to be 0.0.
        assert a["response_rate"] == 0.0

    def test_with_responses_numeric(self):
        trials = (
            [_sacc(True, correct=True, lat=250.0, tdir=SaccadeDirection.LEFT) for _ in range(5)]
            + [_sacc(True, correct=True, lat=300.0, tdir=SaccadeDirection.RIGHT) for _ in range(3)]
            + [_sacc(False) for _ in range(4)]
        )
        a = analyze_prosaccade(trials)
        assert a["response_count"] == 8
        assert a["correct_count"] == 8
        assert a["mean_latency_ms"] is not None
        assert a["min_latency_ms"] == 250.0
        assert a["max_latency_ms"] == 300.0
        assert a["direction_accuracy"] == 1.0


class TestPursuitNull:
    def test_no_usable_cycles_returns_none(self):
        # Cycles with no usable gaze → gain 0 / error 0 → not "valid".
        trials = [
            PursuitTrialRecord(session_id="s", task_id="t", cycle_number=i,
                               mean_pursuit_gain=0.0, mean_position_error_px=0.0,
                               time_on_target_ratio=0.0, catch_up_saccade_count=0)
            for i in range(8)
        ]
        a = analyze_smooth_pursuit(trials)
        assert a["total_cycles"] == 8
        assert a["valid_cycles"] == 0
        assert a["mean_pursuit_gain"] is None
        assert a["mean_position_error_px"] is None

    def test_valid_cycles_numeric(self):
        trials = [
            PursuitTrialRecord(session_id="s", task_id="t", cycle_number=i,
                               mean_pursuit_gain=0.9, mean_position_error_px=40.0,
                               time_on_target_ratio=0.8, catch_up_saccade_count=1)
            for i in range(6)
        ]
        a = analyze_smooth_pursuit(trials)
        assert a["valid_cycles"] == 6
        assert a["mean_pursuit_gain"] == 0.9
        assert a["mean_position_error_px"] == 40.0
