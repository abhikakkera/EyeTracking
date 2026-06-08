"""
Gap-overlap task — v0.3.

Protocol
--------
Two interleaved conditions (randomised trial order):

  GAP condition:
      FIXATION (fixation_duration_sec)
      GAP      (gap_duration_sec)     — fixation OFF, target not yet on
      TARGET   (response_window_sec)  — peripheral target appears
      → "gap effect": gap trials typically produce shorter saccade latencies

  OVERLAP condition:
      FIXATION (fixation_duration_sec)
      TARGET   (response_window_sec)  — fixation stays ON while target appears
      → fixation and target both visible simultaneously

Both conditions record:
  • saccade latency (onset relative to target appearance)
  • response direction (toward/away from target)
  • direction_correct (should always be True; errors = reflexive look away)

The gap_effect can be computed post-hoc from:
  mean_gap_latency_ms - mean_overlap_latency_ms

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

import random
import uuid
from collections import deque
from typing import Deque, List, Optional

from config import AppConfig
from src.data.schema import EyeTestType, FrameRecord
from src.tasks.base_task import BaseTask
from src.tasks.task_schema import (
    SaccadeDirection,
    SaccadeTrialRecord,
    TaskContext,
    TaskPhase,
    TrialCondition,
    TrialRecord,
)


class GapOverlapTask(BaseTask):
    """
    Gap-overlap saccade task.

    half of `num_trials` use the GAP condition;
    the other half use OVERLAP.  Conditions are interleaved randomly.
    """

    TASK_NAME = "Gap-Overlap Task"

    def __init__(self, config: AppConfig) -> None:
        self._cfg        = config.task
        self._task_id    = str(uuid.uuid4())[:8]
        self._session_id = ""
        self._rng        = random.Random(
            None if self._cfg.random_seed < 0 else self._cfg.random_seed
        )

        ecc = self._cfg.target_eccentricity_ratio
        self._left_x  = 0.5 - ecc
        self._right_x = 0.5 + ecc

        # State machine
        self._phase: TaskPhase = TaskPhase.WAITING
        self._trial_num: int   = 0
        self._done             = False

        # Trial plan: list of (direction, condition) tuples
        self._trial_plan: List[tuple] = []
        self._current_trial_id: str = ""
        self._current_target_dir: SaccadeDirection = SaccadeDirection.NONE
        self._current_target_x: float = 0.5
        self._current_condition: TrialCondition = TrialCondition.GAP

        # Phase timing
        self._phase_start_sec: float  = 0.0
        self._fixation_onset_sec: float = 0.0
        self._target_onset_sec: float   = 0.0

        # Response tracking
        self._gaze_at_target_onset: float = 0.5
        self._vel_history: Deque[float] = deque(maxlen=10)
        # Whether fixation dot should still be shown (overlap condition)
        self._show_fixation: bool = True

        # Completed trials
        self._completed: List[SaccadeTrialRecord] = []
        self._pending_trial: Optional[SaccadeTrialRecord] = None
        self._just_completed = False

        self._build_trial_plan()

    # ------------------------------------------------------------------
    # BaseTask properties
    # ------------------------------------------------------------------

    @property
    def task_type(self) -> EyeTestType:
        return EyeTestType.GAP_OVERLAP

    @property
    def task_name(self) -> str:
        return self.TASK_NAME

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def current_phase(self) -> TaskPhase:
        return self._phase

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def trial_number(self) -> int:
        return self._trial_num

    @property
    def num_trials(self) -> int:
        return self._cfg.num_trials

    # ------------------------------------------------------------------
    # Per-frame interface
    # ------------------------------------------------------------------

    def on_tracking_frame(self, record: FrameRecord) -> None:
        self._just_completed = False
        t = record.timestamp_sec

        if self._phase == TaskPhase.WAITING:
            self._start_next_trial(t)

        elif self._phase == TaskPhase.FIXATION:
            elapsed = t - self._phase_start_sec
            if elapsed >= self._cfg.fixation_duration_sec:
                if self._current_condition == TrialCondition.GAP:
                    self._enter_gap(t)
                else:
                    # OVERLAP: fixation stays, target appears simultaneously
                    self._enter_target(t, record, keep_fixation=True)

        elif self._phase == TaskPhase.GAP:
            # Fixation is OFF, target not yet on
            elapsed = t - self._phase_start_sec
            if elapsed >= self._cfg.gap_duration_sec:
                self._enter_target(t, record, keep_fixation=False)

        elif self._phase == TaskPhase.TARGET:
            elapsed = t - self._phase_start_sec
            self._vel_history.append(record.gaze_velocity_px_per_sec)

            if record.face_detected and not record.blink_detected:
                onset = self.detect_saccade_onset(
                    record.gaze_velocity_px_per_sec,
                    list(self._vel_history)[:-1],
                    self._cfg.saccade_velocity_threshold_px_per_sec,
                    self._cfg.saccade_min_below_frames,
                )
                if onset:
                    dx = record.gaze_x - self._gaze_at_target_onset
                    direction = self.gaze_direction_from_delta(dx)
                    correct = (direction == self._current_target_dir)
                    self._record_response(record, t, direction, correct)
                    return

            if elapsed >= self._cfg.response_window_sec:
                self._record_no_response(t)

        elif self._phase == TaskPhase.INTER_TRIAL:
            elapsed = t - self._phase_start_sec
            if elapsed >= self._cfg.inter_trial_interval_sec:
                if self._trial_num >= self._cfg.num_trials:
                    self._phase = TaskPhase.DONE
                    self._done  = True
                else:
                    self._start_next_trial(t)

    def current_context(self) -> TaskContext:
        sw = self._cfg.screen_width
        sh = self._cfg.screen_height
        target_on = self._phase == TaskPhase.TARGET
        # Fixation visible: during FIXATION phase, or during TARGET if OVERLAP
        fix_on = (
            self._phase == TaskPhase.FIXATION
            or self._phase == TaskPhase.WAITING
            or (self._phase == TaskPhase.TARGET and self._show_fixation)
        )
        tx = self._current_target_x if target_on else 0.5
        return TaskContext(
            session_id     = self._session_id,
            task_id        = self._task_id,
            trial_number   = self._trial_num,
            trial_id       = self._current_trial_id,
            task_phase     = self._phase,
            target_visible = target_on,
            target_x       = tx,
            target_y       = self._cfg.fixation_y,
            target_x_px    = tx * sw,
            target_y_px    = self._cfg.fixation_y * sh,
            fixation_visible = fix_on,
            fixation_x     = self._cfg.fixation_x,
            fixation_y     = self._cfg.fixation_y,
        )

    # ------------------------------------------------------------------
    # Trial management
    # ------------------------------------------------------------------

    def trial_just_completed(self) -> bool:
        return self._just_completed

    def pop_completed_trial(self) -> TrialRecord:
        if not self._just_completed or self._pending_trial is None:
            raise ValueError("No trial just completed.")
        t = self._pending_trial
        self._pending_trial = None
        return t

    def get_completed_trials(self) -> List[TrialRecord]:
        return list(self._completed)

    def reset(self) -> None:
        self.__init__(AppConfig())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_trial_plan(self) -> None:
        n    = self._cfg.num_trials
        half = n // 2

        directions  = (
            [SaccadeDirection.LEFT]  * (half // 2) +
            [SaccadeDirection.RIGHT] * (half - half // 2) +
            [SaccadeDirection.LEFT]  * ((n - half) // 2) +
            [SaccadeDirection.RIGHT] * ((n - half) - (n - half) // 2)
        )
        conditions = (
            [TrialCondition.GAP]     * half +
            [TrialCondition.OVERLAP] * (n - half)
        )
        combined = list(zip(directions, conditions))
        self._rng.shuffle(combined)
        self._trial_plan = combined

    def _start_next_trial(self, t: float) -> None:
        self._trial_num += 1
        dir_, cond = self._trial_plan[self._trial_num - 1]
        self._current_trial_id   = str(uuid.uuid4())[:8]
        self._current_target_dir = dir_
        self._current_condition  = cond
        self._current_target_x   = (
            self._left_x if dir_ == SaccadeDirection.LEFT else self._right_x
        )
        self._vel_history.clear()
        self._show_fixation      = True
        self._fixation_onset_sec = t
        self._phase_start_sec    = t
        self._phase              = TaskPhase.FIXATION

    def _enter_gap(self, t: float) -> None:
        """GAP condition: turn fixation OFF, wait before target appears."""
        self._show_fixation   = False
        self._phase_start_sec = t
        self._phase           = TaskPhase.GAP

    def _enter_target(self, t: float, record: FrameRecord, keep_fixation: bool) -> None:
        self._target_onset_sec     = t
        self._phase_start_sec      = t
        self._phase                = TaskPhase.TARGET
        self._show_fixation        = keep_fixation
        self._gaze_at_target_onset = record.gaze_x if record.face_detected else 0.5
        self._vel_history.clear()

    def _record_response(
        self,
        record: FrameRecord,
        t: float,
        direction: SaccadeDirection,
        correct: bool,
    ) -> None:
        trial = SaccadeTrialRecord(
            session_id      = self._session_id,
            task_id         = self._task_id,
            trial_id        = self._current_trial_id,
            trial_number    = self._trial_num,
            condition       = self._current_condition,
            fixation_onset_sec  = self._fixation_onset_sec,
            target_onset_sec    = self._target_onset_sec,
            trial_end_sec       = t,
            response_detected   = True,
            response_onset_sec  = t,
            response_latency_ms = max(0.0, (t - self._target_onset_sec) * 1000.0),
            response_direction  = direction,
            response_velocity_px_per_sec = record.gaze_velocity_px_per_sec,
            target_x            = self._current_target_x,
            target_y            = self._cfg.fixation_y,
            target_direction    = self._current_target_dir,
            direction_correct   = correct,
        )
        self._emit_trial(trial, t)

    def _record_no_response(self, t: float) -> None:
        trial = SaccadeTrialRecord(
            session_id      = self._session_id,
            task_id         = self._task_id,
            trial_id        = self._current_trial_id,
            trial_number    = self._trial_num,
            condition       = self._current_condition,
            fixation_onset_sec  = self._fixation_onset_sec,
            target_onset_sec    = self._target_onset_sec,
            trial_end_sec       = t,
            response_detected   = False,
            target_x            = self._current_target_x,
            target_y            = self._cfg.fixation_y,
            target_direction    = self._current_target_dir,
            direction_correct   = False,
        )
        self._emit_trial(trial, t)

    def _emit_trial(self, trial: SaccadeTrialRecord, t: float) -> None:
        self._completed.append(trial)
        self._pending_trial   = trial
        self._just_completed  = True
        self._phase_start_sec = t
        self._phase           = TaskPhase.INTER_TRIAL
