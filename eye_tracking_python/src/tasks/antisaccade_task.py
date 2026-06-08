"""
Anti-saccade task — v0.3.

Protocol
--------
Identical timing to the pro-saccade task, but the correct response is to
saccade AWAY from (opposite to) the peripheral target.

  FIXATION (fixation_duration_sec)
      → fixation dot at screen centre
  TARGET  (up to response_window_sec)
      → target appears left or right
      → participant should saccade in the OPPOSITE direction
  INTER_TRIAL (inter_trial_interval_sec)

Response classification:
  • Correct   : first saccade away from target (direction != target_direction)
  • Error     : first saccade toward target    (direction == target_direction)
    – SaccadeTrialRecord.error_saccade_detected = True
    – Then we watch for a corrective anti-saccade within the remaining window

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


class AntiSaccadeTask(BaseTask):
    """
    Anti-saccade protocol: saccade AWAY from the peripheral target.

    error_saccade_detected  — reflexive saccade toward target was seen
    correction_made         — a subsequent corrective saccade moved away from target
    direction_correct       — True when the FIRST saccade was the correct anti-saccade
    """

    TASK_NAME = "Anti-Saccade Task"

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

        self._trial_plan: List[SaccadeDirection] = []
        self._current_trial_id: str = ""
        self._current_target_dir: SaccadeDirection = SaccadeDirection.NONE
        self._current_target_x: float = 0.5

        # Phase timing
        self._phase_start_sec: float  = 0.0
        self._fixation_onset_sec: float = 0.0
        self._target_onset_sec: float   = 0.0

        # Response tracking
        self._gaze_at_target_onset: float = 0.5
        self._vel_history: Deque[float] = deque(maxlen=10)
        self._error_detected    = False
        self._error_onset_gaze_x: float = 0.5

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
        return EyeTestType.ANTISACCADE

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
                self._enter_target(t, record)

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

                    if not self._error_detected:
                        # First saccade in the response window
                        is_toward_target = (direction == self._current_target_dir)
                        if is_toward_target:
                            # Error: reflexive saccade toward target
                            self._error_detected = True
                            self._error_onset_gaze_x = record.gaze_x
                            # Don't end trial yet — wait for correction or timeout
                        else:
                            # Correct anti-saccade on first try
                            self._record_response(
                                record, t, direction,
                                error=False, correction=False,
                            )
                            return
                    else:
                        # Second saccade after an error — check for correction
                        dx2 = record.gaze_x - self._error_onset_gaze_x
                        corr_dir = self.gaze_direction_from_delta(dx2)
                        correct_anti = (corr_dir != self._current_target_dir
                                        and corr_dir != SaccadeDirection.NONE)
                        self._record_response(
                            record, t, direction,
                            error=True, correction=correct_anti,
                        )
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
        fix_on    = self._phase in (TaskPhase.FIXATION, TaskPhase.WAITING)
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
        plan = [SaccadeDirection.LEFT] * half + [SaccadeDirection.RIGHT] * (n - half)
        self._rng.shuffle(plan)
        self._trial_plan = plan

    def _start_next_trial(self, t: float) -> None:
        self._trial_num += 1
        dir_ = self._trial_plan[self._trial_num - 1]
        self._current_trial_id   = str(uuid.uuid4())[:8]
        self._current_target_dir = dir_
        self._current_target_x   = (
            self._left_x if dir_ == SaccadeDirection.LEFT else self._right_x
        )
        self._vel_history.clear()
        self._error_detected     = False
        self._fixation_onset_sec = t
        self._phase_start_sec    = t
        self._phase              = TaskPhase.FIXATION

    def _enter_target(self, t: float, record: FrameRecord) -> None:
        self._target_onset_sec    = t
        self._phase_start_sec     = t
        self._phase               = TaskPhase.TARGET
        self._gaze_at_target_onset = record.gaze_x if record.face_detected else 0.5
        self._vel_history.clear()

    def _record_response(
        self,
        record: FrameRecord,
        t: float,
        direction: SaccadeDirection,
        error: bool,
        correction: bool,
    ) -> None:
        # direction_correct = True only if first saccade was the anti-saccade
        correct = not error
        trial = SaccadeTrialRecord(
            session_id      = self._session_id,
            task_id         = self._task_id,
            trial_id        = self._current_trial_id,
            trial_number    = self._trial_num,
            condition       = TrialCondition.NONE,
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
            error_saccade_detected = error,
            correction_made     = correction,
        )
        self._emit_trial(trial, t)

    def _record_no_response(self, t: float) -> None:
        trial = SaccadeTrialRecord(
            session_id      = self._session_id,
            task_id         = self._task_id,
            trial_id        = self._current_trial_id,
            trial_number    = self._trial_num,
            condition       = TrialCondition.NONE,
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
