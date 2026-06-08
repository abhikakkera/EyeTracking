"""
Smooth pursuit task — v0.3.

Protocol
--------
A moving target follows a configurable path (horizontal sine, vertical,
circular, figure-8).  The session consists of `pursuit_num_cycles` complete
cycles.  Each cycle is recorded as a PursuitTrialRecord.

Per-frame:
  • target position computed from elapsed time + path formula
  • TaskContext records target_x, target_y every frame
  • Gaze velocity direction vs target velocity direction → pursuit gain

Per-cycle metrics (PursuitTrialRecord):
  • mean_pursuit_gain       — mean(|gaze_vel|) / mean(|target_vel|)
  • mean_position_error_px  — mean distance in pixels (requires calibration
                               for absolute accuracy; still useful comparatively)
  • time_on_target_ratio    — fraction of frames within gaze_error_threshold
  • catch_up_saccade_count  — velocity spikes above threshold during pursuit

Paths
-----
  "horizontal" — x = cx + A·sin(2π·f·t),  y = centre
  "vertical"   — x = centre,               y = cy + A·sin(2π·f·t)
  "circular"   — x = cx + A·cos(2π·f·t),  y = cy + A·sin(2π·f·t)
  "figure8"    — x = cx + A·sin(2π·f·t),  y = cy + A/2·sin(4π·f·t)

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

import math
import uuid
from typing import List, Optional, Tuple

from config import AppConfig
from src.data.schema import EyeTestType, FrameRecord
from src.tasks.base_task import BaseTask
from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    TaskContext,
    TaskPhase,
    TrialCondition,
    TrialRecord,
)

# If gaze velocity > this fraction of target velocity → catch-up saccade
_CATCHUP_VEL_RATIO = 3.0
# Gaze error threshold for "on target" (normalized units × screen width)
_ON_TARGET_THRESHOLD_PX = 80.0


class SmoothPursuitTask(BaseTask):
    """
    Smooth pursuit protocol: follow a moving target for N cycles.
    """

    TASK_NAME = "Smooth Pursuit Task"

    def __init__(self, config: AppConfig) -> None:
        self._cfg        = config.task
        self._task_id    = str(uuid.uuid4())[:8]
        self._session_id = ""

        self._phase: TaskPhase = TaskPhase.WAITING
        self._done = False

        # Cycle tracking
        self._cycle_num: int = 0
        self._trial_num: int = 0   # same as cycle_num for pursuit
        self._cycle_start_sec: float = 0.0
        self._session_start_sec: float = 0.0

        self._period_sec: float = 1.0 / max(self._cfg.pursuit_speed_cycles_per_sec, 0.01)
        self._amp = self._cfg.pursuit_amplitude_ratio   # normalized [0,1]

        # Current frame's target position
        self._target_x: float = 0.5
        self._target_y: float = 0.5
        self._prev_target_x: float = 0.5
        self._prev_target_y: float = 0.5

        # Per-cycle accumulators
        self._cycle_gaze_vels: List[float]   = []
        self._cycle_target_vels: List[float] = []
        self._cycle_errors_px: List[float]   = []
        self._cycle_on_target: List[bool]    = []
        self._cycle_saccade_count: int       = 0
        self._in_saccade: bool               = False

        # Trial plan (one entry per cycle)
        self._current_trial_id: str = ""

        # Completed trials
        self._completed: List[PursuitTrialRecord] = []
        self._pending_trial: Optional[PursuitTrialRecord] = None
        self._just_completed = False

    # ------------------------------------------------------------------
    # BaseTask properties
    # ------------------------------------------------------------------

    @property
    def task_type(self) -> EyeTestType:
        return EyeTestType.SMOOTH_PURSUIT

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
        return self._cycle_num

    @property
    def num_trials(self) -> int:
        return self._cfg.pursuit_num_cycles

    # ------------------------------------------------------------------
    # Per-frame interface
    # ------------------------------------------------------------------

    def on_tracking_frame(self, record: FrameRecord) -> None:
        self._just_completed = False
        t = record.timestamp_sec

        if self._phase == TaskPhase.WAITING:
            self._session_start_sec = t
            self._start_cycle(t)
            return

        if self._phase != TaskPhase.TARGET:
            return

        elapsed_in_cycle = t - self._cycle_start_sec

        # Compute target velocity (normalized per second)
        prev_x, prev_y = self._target_x, self._target_y
        self._target_x, self._target_y = self._target_position(t)
        dt = max(record.timestamp_sec - (t - 1.0 / 30.0), 1e-3)  # approx dt

        # Convert normalized velocity → approximate pixels/sec
        sw = self._cfg.screen_width
        sh = self._cfg.screen_height
        target_vel_px = (
            abs(self._target_x - prev_x) * sw +
            abs(self._target_y - prev_y) * sh
        ) / max(dt, 1e-4)

        # Gaze vs target velocity
        gaze_vel = record.gaze_velocity_px_per_sec

        # Catch-up saccade detection (velocity spike relative to target motion)
        is_saccade = (
            target_vel_px > 10 and
            gaze_vel > _CATCHUP_VEL_RATIO * target_vel_px
        )
        if is_saccade and not self._in_saccade:
            self._cycle_saccade_count += 1
        self._in_saccade = is_saccade

        # Position error (gaze vs target in normalized units → pixels)
        if record.face_detected and not record.blink_detected:
            err_px = math.hypot(
                (record.gaze_x - self._target_x) * sw,
                (record.gaze_y - self._target_y) * sh,
            )
            self._cycle_errors_px.append(err_px)
            self._cycle_on_target.append(err_px < _ON_TARGET_THRESHOLD_PX)

            if not is_saccade:
                self._cycle_gaze_vels.append(gaze_vel)
                self._cycle_target_vels.append(target_vel_px)

        # Check cycle end
        if elapsed_in_cycle >= self._period_sec:
            self._end_cycle(t)

    def current_context(self) -> TaskContext:
        sw = self._cfg.screen_width
        sh = self._cfg.screen_height
        x, y = self._target_x, self._target_y
        return TaskContext(
            session_id     = self._session_id,
            task_id        = self._task_id,
            trial_number   = self._cycle_num,
            trial_id       = self._current_trial_id,
            task_phase     = self._phase,
            target_visible = (self._phase == TaskPhase.TARGET),
            target_x       = x,
            target_y       = y,
            target_x_px    = x * sw,
            target_y_px    = y * sh,
            fixation_visible = False,
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

    def _start_cycle(self, t: float) -> None:
        self._cycle_num += 1
        self._trial_num  = self._cycle_num
        self._current_trial_id = str(uuid.uuid4())[:8]
        self._cycle_start_sec  = t
        self._phase            = TaskPhase.TARGET

        self._cycle_gaze_vels   = []
        self._cycle_target_vels = []
        self._cycle_errors_px   = []
        self._cycle_on_target   = []
        self._cycle_saccade_count = 0
        self._in_saccade          = False

        # Initialise target position
        self._target_x, self._target_y = self._target_position(t)

    def _end_cycle(self, t: float) -> None:
        """Finalise current cycle → PursuitTrialRecord."""
        gv  = self._cycle_gaze_vels
        tv  = self._cycle_target_vels
        errs = self._cycle_errors_px
        on   = self._cycle_on_target

        # Pursuit gain: ratio of smoothed gaze velocity to target velocity
        if tv and sum(tv) > 0:
            mean_gain = sum(gv) / len(gv) / (sum(tv) / len(tv)) if gv else 0.0
        else:
            mean_gain = 0.0

        target_peak = max(tv) if tv else 0.0
        mean_err    = sum(errs) / len(errs) if errs else 0.0
        on_ratio    = sum(1 for x in on if x) / max(len(on), 1)

        trial = PursuitTrialRecord(
            session_id      = self._session_id,
            task_id         = self._task_id,
            trial_id        = self._current_trial_id,
            trial_number    = self._cycle_num,
            condition       = TrialCondition.NONE,
            target_onset_sec = self._cycle_start_sec,
            trial_end_sec    = t,
            response_detected = True,
            cycle_number     = self._cycle_num,
            target_peak_velocity_px_per_sec = round(target_peak, 2),
            mean_pursuit_gain     = round(max(0.0, mean_gain), 3),
            mean_position_error_px = round(mean_err, 2),
            time_on_target_ratio   = round(on_ratio, 3),
            catch_up_saccade_count = self._cycle_saccade_count,
        )
        self._completed.append(trial)
        self._pending_trial  = trial
        self._just_completed = True

        if self._cycle_num >= self._cfg.pursuit_num_cycles:
            self._phase = TaskPhase.DONE
            self._done  = True
        else:
            self._start_cycle(t)

    def _target_position(self, t: float) -> Tuple[float, float]:
        """
        Compute normalised [0,1] target position at absolute time t.
        All paths oscillate around (0.5, 0.5).
        """
        elapsed = t - self._session_start_sec
        f   = self._cfg.pursuit_speed_cycles_per_sec
        amp = self._amp
        cx  = self._cfg.fixation_x
        cy  = self._cfg.fixation_y
        pattern = self._cfg.pursuit_pattern.lower()

        phase = 2.0 * math.pi * f * elapsed

        if pattern == "horizontal":
            x = cx + amp * math.sin(phase)
            y = cy
        elif pattern == "vertical":
            x = cx
            y = cy + amp * math.sin(phase)
        elif pattern == "circular":
            x = cx + amp * math.cos(phase)
            y = cy + amp * math.sin(phase)
        elif pattern == "figure8":
            x = cx + amp * math.sin(phase)
            y = cy + (amp / 2.0) * math.sin(2.0 * phase)
        else:
            # Default fallback = horizontal
            x = cx + amp * math.sin(phase)
            y = cy

        # Clamp to visible screen area
        margin = 0.05
        x = max(margin, min(1.0 - margin, x))
        y = max(margin, min(1.0 - margin, y))
        return x, y
