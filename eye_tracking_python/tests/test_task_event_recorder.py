"""
Tests for backend.services.task_event_recorder — reconstructing trial records
from streamed web frames + browser events (no camera, pure data).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.services.task_event_recorder import (
    WebFrame,
    build_task_contexts,
    reconstruct_trials,
)
from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    SaccadeTrialRecord,
)

SW, SH = 1280, 720
THR = 0.06


def _frame(ts, gaze_x, phase, tid="t1", tdir="right", target_x=0.85, face=True, gaze_y=0.5, target_y=0.5):
    return WebFrame(
        browser_ts_ms=ts, gaze_x=gaze_x, gaze_y=gaze_y, task_phase=phase,
        trial_id=tid, target_direction=tdir, target_x=target_x, target_y=target_y,
        face_detected=face, blink=False, velocity_px_s=300.0,
    )


# ---------------------------------------------------------------------------
# Pro-saccade
# ---------------------------------------------------------------------------

def test_prosaccade_correct_response():
    events = [
        {"type": "task_started", "timestamp_ms": 0.0},
        {"type": "trial_started", "timestamp_ms": 1000.0, "trial_id": "t1",
         "trial_number": 1, "direction": "right", "condition": "none"},
        {"type": "fixation_shown", "timestamp_ms": 1000.0, "trial_id": "t1"},
        {"type": "target_shown", "timestamp_ms": 2000.0, "trial_id": "t1",
         "target_x": 0.85, "target_y": 0.5},
        {"type": "trial_ended", "timestamp_ms": 2800.0, "trial_id": "t1"},
    ]
    frames = [_frame(t, 0.5, "fixation") for t in range(1000, 2000, 100)]
    frames += [_frame(t, 0.72, "target") for t in range(2050, 2400, 50)]

    trials = reconstruct_trials("prosaccade", "s", "tk", frames, events, THR, SW, SH)
    assert len(trials) == 1
    tr = trials[0]
    assert isinstance(tr, SaccadeTrialRecord)
    assert tr.response_detected is True
    assert tr.response_direction == SaccadeDirection.RIGHT
    assert tr.direction_correct is True
    assert 0 < tr.response_latency_ms <= 100


def test_prosaccade_no_response():
    events = [
        {"type": "trial_started", "timestamp_ms": 1000.0, "trial_id": "t1",
         "trial_number": 1, "direction": "left"},
        {"type": "target_shown", "timestamp_ms": 2000.0, "trial_id": "t1", "target_x": 0.15},
        {"type": "trial_ended", "timestamp_ms": 2800.0, "trial_id": "t1"},
    ]
    # Gaze never moves away from center
    frames = [_frame(t, 0.5, "target", tdir="left", target_x=0.15) for t in range(2000, 2700, 50)]
    trials = reconstruct_trials("prosaccade", "s", "tk", frames, events, THR, SW, SH)
    assert trials[0].response_detected is False
    assert trials[0].direction_correct is False


# ---------------------------------------------------------------------------
# Anti-saccade
# ---------------------------------------------------------------------------

def test_antisaccade_error_then_correction():
    events = [
        {"type": "trial_started", "timestamp_ms": 1000.0, "trial_id": "t1",
         "trial_number": 1, "direction": "right"},
        {"type": "target_shown", "timestamp_ms": 2000.0, "trial_id": "t1", "target_x": 0.85},
        {"type": "trial_ended", "timestamp_ms": 3000.0, "trial_id": "t1"},
    ]
    frames = [_frame(t, 0.5, "fixation", tdir="right") for t in range(1000, 2000, 100)]
    # Reflexive look TOWARD target (right) = error
    frames += [_frame(t, 0.72, "target", tdir="right") for t in range(2050, 2200, 50)]
    # Then correct away (left)
    frames += [_frame(t, 0.30, "target", tdir="right") for t in range(2300, 2600, 50)]

    trials = reconstruct_trials("antisaccade", "s", "tk", frames, events, THR, SW, SH)
    tr = trials[0]
    assert tr.response_detected is True
    assert tr.error_saccade_detected is True       # looked toward target first
    assert tr.direction_correct is False
    assert tr.correction_made is True              # later moved opposite


def test_antisaccade_correct_first_try():
    events = [
        {"type": "trial_started", "timestamp_ms": 1000.0, "trial_id": "t1",
         "trial_number": 1, "direction": "right"},
        {"type": "target_shown", "timestamp_ms": 2000.0, "trial_id": "t1", "target_x": 0.85},
        {"type": "trial_ended", "timestamp_ms": 3000.0, "trial_id": "t1"},
    ]
    frames = [_frame(t, 0.5, "fixation", tdir="right") for t in range(1000, 2000, 100)]
    # Look AWAY (left) = correct anti-saccade
    frames += [_frame(t, 0.28, "target", tdir="right") for t in range(2050, 2400, 50)]

    tr = reconstruct_trials("antisaccade", "s", "tk", frames, events, THR, SW, SH)[0]
    assert tr.direction_correct is True
    assert tr.error_saccade_detected is False


# ---------------------------------------------------------------------------
# Smooth pursuit
# ---------------------------------------------------------------------------

def test_pursuit_perfect_tracking_gain_near_one():
    events = [
        {"type": "trial_started", "timestamp_ms": 0.0, "trial_id": "c1",
         "trial_number": 1, "cycle_number": 1},
        {"type": "trial_ended", "timestamp_ms": 1000.0, "trial_id": "c1"},
    ]
    # Gaze exactly equals target each frame → gain ~1.0, error ~0
    frames = []
    for i, t in enumerate(range(0, 1000, 50)):
        x = 0.3 + 0.004 * i
        frames.append(WebFrame(
            browser_ts_ms=t, trial_id="c1", task_phase="target",
            gaze_x=x, gaze_y=0.5, target_x=x, target_y=0.5, face_detected=True,
        ))
    trials = reconstruct_trials("smooth_pursuit", "s", "tk", frames, events, THR, SW, SH)
    assert len(trials) == 1
    tr = trials[0]
    assert isinstance(tr, PursuitTrialRecord)
    assert tr.mean_position_error_px == 0.0
    assert tr.time_on_target_ratio == 1.0
    assert 0.9 <= tr.mean_pursuit_gain <= 1.1


# ---------------------------------------------------------------------------
# TaskContext build
# ---------------------------------------------------------------------------

def test_build_task_contexts():
    frames = [_frame(1000, 0.5, "fixation"), _frame(2050, 0.7, "target")]
    ctxs = build_task_contexts("s", "tk", frames, SW, SH)
    assert len(ctxs) == 2
    assert ctxs[1].task_phase.value == "target"
    assert ctxs[1].target_x_px == 0.85 * SW
