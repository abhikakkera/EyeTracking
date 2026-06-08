"""
Abstract base class for all structured eye-movement tasks — v0.3.

Concrete sub-classes implement:
  • on_tracking_frame(record) — advance state machine, detect responses
  • current_context()         — return stimulus state for this frame
  • get_completed_trials()    — list of completed TrialRecord objects

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.data.schema import EyeTestType, FrameRecord
from src.tasks.task_schema import (
    SaccadeDirection,
    TaskContext,
    TaskPhase,
    TrialRecord,
)


class BaseTask(ABC):
    """
    Abstract base for all structured task protocols.

    The TaskRunner calls:
        task.on_tracking_frame(record)     # every camera frame
        ctx = task.current_context()       # get stimulus + trial state
        if task.trial_just_completed():
            t = task.pop_completed_trial()
    """

    # ------------------------------------------------------------------
    # Sub-class must declare these class attributes
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def task_type(self) -> EyeTestType:
        """EyeTestType enum value for this protocol."""

    @property
    @abstractmethod
    def task_name(self) -> str:
        """Human-readable name shown in the stimulus window."""

    @property
    @abstractmethod
    def task_id(self) -> str:
        """Unique ID for this task run (assigned by TaskRunner)."""

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def current_phase(self) -> TaskPhase:
        """Current state-machine phase."""

    @property
    @abstractmethod
    def is_done(self) -> bool:
        """True when all trials are complete."""

    @property
    @abstractmethod
    def trial_number(self) -> int:
        """1-based index of the current or last trial (0 = not started)."""

    @property
    @abstractmethod
    def num_trials(self) -> int:
        """Total number of trials in this session."""

    # ------------------------------------------------------------------
    # Per-frame interface (called by TaskRunner)
    # ------------------------------------------------------------------

    @abstractmethod
    def on_tracking_frame(self, record: FrameRecord) -> None:
        """
        Advance the task state machine.
        Called once per camera frame with the current FrameRecord.
        """

    @abstractmethod
    def current_context(self) -> TaskContext:
        """
        Return the current task context for this frame.
        TaskRunner records this alongside FrameRecord in task_frames.csv.
        Also used to build the stimulus display.
        """

    # ------------------------------------------------------------------
    # Trial management
    # ------------------------------------------------------------------

    @abstractmethod
    def trial_just_completed(self) -> bool:
        """True during the single frame when a trial transitions to complete."""

    @abstractmethod
    def pop_completed_trial(self) -> TrialRecord:
        """
        Return and consume the most recently completed trial.
        Raises ValueError if trial_just_completed() is False.
        """

    def get_completed_trials(self) -> List[TrialRecord]:
        """Return all completed trials so far (read-only view)."""
        return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def reset(self) -> None:
        """Reset to initial state for a new session."""

    # ------------------------------------------------------------------
    # Shared saccade-onset helper
    # ------------------------------------------------------------------

    @staticmethod
    def detect_saccade_onset(
        current_velocity_px_per_sec: float,
        velocity_history: list,
        threshold: float,
        min_below_frames: int,
    ) -> bool:
        """
        Return True if a saccade onset is detected on this frame.

        Onset requires:
          • current velocity > threshold
          • at least `min_below_frames` previous frames were below threshold
            (ensures we only count the START of a new saccade, not its
             continuation or a prior unfinished one)

        Parameters
        ----------
        current_velocity_px_per_sec : velocity for this frame
        velocity_history            : list of recent velocities (oldest first)
        threshold                   : onset threshold in px/sec
        min_below_frames            : frames that must be below threshold
        """
        if current_velocity_px_per_sec <= threshold:
            return False
        # Need at least min_below_frames consecutive sub-threshold frames
        tail = velocity_history[-min_below_frames:]
        if len(tail) < min_below_frames:
            return False
        return all(v <= threshold for v in tail)

    @staticmethod
    def gaze_direction_from_delta(dx: float) -> SaccadeDirection:
        """Map a signed horizontal gaze delta to SaccadeDirection."""
        if dx > 0.01:
            return SaccadeDirection.RIGHT
        if dx < -0.01:
            return SaccadeDirection.LEFT
        return SaccadeDirection.NONE
