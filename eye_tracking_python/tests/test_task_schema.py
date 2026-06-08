"""
Tests for task_schema.py and the four task state machines.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import AppConfig
from src.data.schema import FrameQuality, FrameRecord
from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    SaccadeTrialRecord,
    TaskContext,
    TaskPhase,
    TrialCondition,
)
from src.tasks.prosaccade_task import ProSaccadeTask
from src.tasks.antisaccade_task import AntiSaccadeTask
from src.tasks.gap_overlap_task import GapOverlapTask
from src.tasks.smooth_pursuit_task import SmoothPursuitTask
from src.tasks.base_task import BaseTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    frame: int = 0,
    t: float = 0.0,
    velocity: float = 0.0,
    gaze_x: float = 0.5,
    face_detected: bool = True,
) -> FrameRecord:
    return FrameRecord(
        session_id="test",
        frame_number=frame,
        timestamp_sec=t,
        face_detected=face_detected,
        gaze_x=gaze_x,
        gaze_y=0.5,
        gaze_velocity_px_per_sec=velocity,
        frame_quality=FrameQuality.GOOD,
    )


def _fast_saccade(task: BaseTask, t_start: float, t_end: float, gaze_x: float) -> None:
    """
    Feed frames to a task: first N frames with low velocity (sub-threshold),
    then one frame with high velocity (supra-threshold onset).
    Simulates a saccade onset.
    """
    cfg = task._cfg
    # Sub-threshold frames
    for i in range(cfg.saccade_min_below_frames + 1):
        task.on_tracking_frame(_make_record(i, t_start + i * 0.033, velocity=50.0))
    # Supra-threshold frame = onset
    task.on_tracking_frame(_make_record(
        100, t_end, velocity=cfg.saccade_velocity_threshold_px_per_sec + 100,
        gaze_x=gaze_x,
    ))


# ---------------------------------------------------------------------------
# TaskContext
# ---------------------------------------------------------------------------

class TestTaskContext:
    def test_defaults(self):
        ctx = TaskContext()
        assert ctx.task_phase == TaskPhase.WAITING
        assert not ctx.target_visible
        assert not ctx.fixation_visible
        assert ctx.trial_number == -1

    def test_fields_set(self):
        ctx = TaskContext(
            session_id="s1",
            trial_number=3,
            task_phase=TaskPhase.TARGET,
            target_visible=True,
            target_x=0.15,
        )
        assert ctx.target_x == 0.15
        assert ctx.task_phase == TaskPhase.TARGET
        assert ctx.target_visible is True


# ---------------------------------------------------------------------------
# SaccadeTrialRecord
# ---------------------------------------------------------------------------

class TestSaccadeTrialRecord:
    def test_defaults(self):
        t = SaccadeTrialRecord(session_id="s", task_id="t")
        assert t.condition == TrialCondition.NONE
        assert t.direction_correct is False
        assert t.error_saccade_detected is False
        assert t.response_direction == SaccadeDirection.NONE

    def test_has_unique_trial_id(self):
        a = SaccadeTrialRecord(session_id="s", task_id="t")
        b = SaccadeTrialRecord(session_id="s", task_id="t")
        assert a.trial_id != b.trial_id


# ---------------------------------------------------------------------------
# ProSaccadeTask
# ---------------------------------------------------------------------------

class TestProSaccadeTask:
    def setup_method(self):
        cfg = AppConfig()
        cfg.task.num_trials = 4
        cfg.task.fixation_duration_sec = 0.05
        cfg.task.target_duration_sec = 0.5
        cfg.task.response_window_sec = 0.5
        cfg.task.inter_trial_interval_sec = 0.05
        cfg.task.random_seed = 42
        cfg.task.saccade_velocity_threshold_px_per_sec = 200.0
        cfg.task.saccade_min_below_frames = 2
        self.task = ProSaccadeTask(cfg)

    def test_initial_state(self):
        assert self.task.current_phase == TaskPhase.WAITING
        assert not self.task.is_done
        assert self.task.trial_number == 0

    def test_task_type(self):
        from src.data.schema import EyeTestType
        assert self.task.task_type == EyeTestType.PROSACCADE

    def test_transitions_to_fixation(self):
        self.task.on_tracking_frame(_make_record(0, 0.0))
        assert self.task.current_phase == TaskPhase.FIXATION
        assert self.task.trial_number == 1

    def test_context_has_fixation_visible_during_fixation(self):
        self.task.on_tracking_frame(_make_record(0, 0.0))
        ctx = self.task.current_context()
        assert ctx.fixation_visible is True
        assert ctx.target_visible is False

    def test_transitions_to_target_after_fixation(self):
        t = 0.0
        self.task.on_tracking_frame(_make_record(0, t))  # WAITING → FIXATION
        t += 0.10  # after fixation_duration_sec (0.05)
        self.task.on_tracking_frame(_make_record(1, t))
        assert self.task.current_phase == TaskPhase.TARGET

    def test_no_response_trial(self):
        t = 0.0
        self.task.on_tracking_frame(_make_record(0, t))  # → FIXATION
        t += 0.10
        self.task.on_tracking_frame(_make_record(1, t))  # → TARGET
        t += 0.60  # exceeds response_window_sec (0.5)
        self.task.on_tracking_frame(_make_record(2, t))  # → INTER_TRIAL
        assert self.task.current_phase == TaskPhase.INTER_TRIAL
        assert self.task.trial_just_completed()
        trial = self.task.pop_completed_trial()
        assert isinstance(trial, SaccadeTrialRecord)
        assert not trial.response_detected
        assert not trial.direction_correct

    def test_correct_response_detected(self):
        cfg = AppConfig()
        cfg.task.num_trials = 2
        cfg.task.fixation_duration_sec = 0.05
        cfg.task.response_window_sec = 1.0
        cfg.task.inter_trial_interval_sec = 0.05
        cfg.task.random_seed = 1
        cfg.task.saccade_velocity_threshold_px_per_sec = 200.0
        cfg.task.saccade_min_below_frames = 2
        task = ProSaccadeTask(cfg)

        # WAITING → FIXATION
        task.on_tracking_frame(_make_record(0, 0.0))
        # fixation expires
        task.on_tracking_frame(_make_record(1, 0.10))
        assert task.current_phase == TaskPhase.TARGET
        target_dir = task._current_target_dir

        # Low-velocity frames to reset onset
        for i in range(cfg.task.saccade_min_below_frames + 1):
            task.on_tracking_frame(_make_record(10 + i, 0.11 + i * 0.033,
                                                velocity=50.0))
        # Saccade onset toward target
        gaze_x = 0.15 if target_dir == SaccadeDirection.LEFT else 0.85
        task.on_tracking_frame(_make_record(
            99, 0.30, velocity=400.0, gaze_x=gaze_x
        ))
        assert task.trial_just_completed()
        trial = task.pop_completed_trial()
        assert trial.response_detected
        assert trial.direction_correct


# ---------------------------------------------------------------------------
# AntiSaccadeTask
# ---------------------------------------------------------------------------

class TestAntiSaccadeTask:
    def test_error_detected(self):
        cfg = AppConfig()
        cfg.task.num_trials = 2
        cfg.task.fixation_duration_sec = 0.05
        cfg.task.response_window_sec = 1.0
        cfg.task.inter_trial_interval_sec = 0.05
        cfg.task.random_seed = 0
        cfg.task.saccade_velocity_threshold_px_per_sec = 200.0
        cfg.task.saccade_min_below_frames = 2
        task = AntiSaccadeTask(cfg)

        # → FIXATION
        task.on_tracking_frame(_make_record(0, 0.0))
        # → TARGET
        task.on_tracking_frame(_make_record(1, 0.10))
        assert task.current_phase == TaskPhase.TARGET

        target_dir = task._current_target_dir
        # Sub-threshold frames
        for i in range(3):
            task.on_tracking_frame(_make_record(10 + i, 0.11 + i * 0.033, velocity=50.0))

        # Saccade TOWARD target = error
        gaze_x = 0.15 if target_dir == SaccadeDirection.LEFT else 0.85
        task.on_tracking_frame(_make_record(99, 0.30, velocity=400.0, gaze_x=gaze_x))
        # Should NOT yet complete (waiting for correction or timeout)
        assert task._error_detected is True
        assert not task.trial_just_completed()

    def test_task_type(self):
        from src.data.schema import EyeTestType
        task = AntiSaccadeTask(AppConfig())
        assert task.task_type == EyeTestType.ANTISACCADE


# ---------------------------------------------------------------------------
# GapOverlapTask
# ---------------------------------------------------------------------------

class TestGapOverlapTask:
    def test_task_type(self):
        from src.data.schema import EyeTestType
        task = GapOverlapTask(AppConfig())
        assert task.task_type == EyeTestType.GAP_OVERLAP

    def test_gap_phase_exists(self):
        cfg = AppConfig()
        cfg.task.num_trials = 2
        cfg.task.fixation_duration_sec = 0.05
        cfg.task.gap_duration_sec = 0.05
        cfg.task.response_window_sec = 0.5
        cfg.task.inter_trial_interval_sec = 0.05
        cfg.task.random_seed = 99
        task = GapOverlapTask(cfg)

        # Find a GAP trial
        while True:
            task.on_tracking_frame(_make_record(0, 0.0))  # → FIXATION or stays
            if task.current_phase == TaskPhase.FIXATION:
                if task._current_condition == TrialCondition.GAP:
                    break
            task.reset()

        # fixation expires
        task.on_tracking_frame(_make_record(1, 0.10))
        assert task.current_phase == TaskPhase.GAP
        ctx = task.current_context()
        assert not ctx.fixation_visible
        assert not ctx.target_visible


# ---------------------------------------------------------------------------
# SmoothPursuitTask
# ---------------------------------------------------------------------------

class TestSmoothPursuitTask:
    def test_task_type(self):
        from src.data.schema import EyeTestType
        task = SmoothPursuitTask(AppConfig())
        assert task.task_type == EyeTestType.SMOOTH_PURSUIT

    def test_target_moves(self):
        cfg = AppConfig()
        cfg.task.pursuit_pattern = "horizontal"
        cfg.task.pursuit_speed_cycles_per_sec = 1.0  # fast for testing
        cfg.task.pursuit_amplitude_ratio = 0.3
        cfg.task.pursuit_num_cycles = 2
        task = SmoothPursuitTask(cfg)

        # WAITING → starts first cycle
        task.on_tracking_frame(_make_record(0, 0.0))
        assert task.current_phase == TaskPhase.TARGET

        ctx0 = task.current_context()
        # Advance a quarter period (sin goes from 0 → 1, so target_x must change)
        # period = 1/1.0 = 1.0s; quarter = 0.25s
        task.on_tracking_frame(_make_record(1, 0.25))
        ctx1 = task.current_context()
        # Target should have moved
        assert ctx0.target_x != ctx1.target_x

    def test_cycle_completes(self):
        cfg = AppConfig()
        cfg.task.pursuit_speed_cycles_per_sec = 2.0  # period = 0.5s
        cfg.task.pursuit_num_cycles = 1
        cfg.task.pursuit_amplitude_ratio = 0.3
        task = SmoothPursuitTask(cfg)

        task.on_tracking_frame(_make_record(0, 0.0))   # start
        task.on_tracking_frame(_make_record(1, 0.6))   # past one period
        assert task.trial_just_completed() or task.is_done


# ---------------------------------------------------------------------------
# BaseTask.detect_saccade_onset
# ---------------------------------------------------------------------------

class TestSaccadeOnsetDetection:
    def test_no_onset_below_threshold(self):
        result = BaseTask.detect_saccade_onset(100.0, [50.0, 50.0, 50.0], 200.0, 3)
        assert result is False

    def test_onset_above_threshold_with_history(self):
        result = BaseTask.detect_saccade_onset(500.0, [50.0, 50.0, 50.0], 200.0, 3)
        assert result is True

    def test_no_onset_insufficient_history(self):
        result = BaseTask.detect_saccade_onset(500.0, [50.0], 200.0, 3)
        assert result is False

    def test_no_onset_history_has_supra_threshold(self):
        result = BaseTask.detect_saccade_onset(500.0, [50.0, 300.0, 50.0], 200.0, 3)
        assert result is False

    def test_direction_right(self):
        assert BaseTask.gaze_direction_from_delta(0.05) == SaccadeDirection.RIGHT

    def test_direction_left(self):
        assert BaseTask.gaze_direction_from_delta(-0.05) == SaccadeDirection.LEFT

    def test_direction_none(self):
        assert BaseTask.gaze_direction_from_delta(0.005) == SaccadeDirection.NONE
