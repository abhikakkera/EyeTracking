"""
Data schema for structured eye-movement task protocols — v0.3.

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Task-level enumerations
# ---------------------------------------------------------------------------

class TaskPhase(str, Enum):
    """State-machine phase for all saccade/pursuit tasks."""
    WAITING      = "waiting"      # before session begins (distance check)
    FIXATION     = "fixation"     # fixation dot shown, participant must fixate
    GAP          = "gap"          # fixation off, target not yet on (gap-overlap only)
    TARGET       = "target"       # target on screen, response window open
    INTER_TRIAL  = "inter_trial"  # blank screen between trials
    DONE         = "done"         # all trials complete


class TrialCondition(str, Enum):
    """Used by GapOverlapTask to label each trial's condition."""
    GAP     = "gap"       # fixation disappears before target
    OVERLAP = "overlap"   # fixation stays while target appears
    NONE    = "none"      # not applicable (pro/anti-saccade)


class SaccadeDirection(str, Enum):
    LEFT  = "left"
    RIGHT = "right"
    NONE  = "none"   # no response detected


# ---------------------------------------------------------------------------
# Per-frame task context (what the TaskRunner records alongside FrameRecord)
# ---------------------------------------------------------------------------

@dataclass
class TaskContext:
    """
    Snapshot of the task's current stimulus state for one frame.
    Written to task_frames.csv alongside the matching FrameRecord.
    Joined by frame_number.
    """
    session_id: str = ""
    task_id: str = ""
    frame_number: int = 0
    timestamp_sec: float = 0.0

    # Trial position
    trial_number: int = -1   # -1 means between trials / WAITING
    trial_id: str = ""
    task_phase: TaskPhase = TaskPhase.WAITING

    # Stimulus state
    target_visible: bool = False
    target_x: float = 0.5    # normalized [0, 1] in stimulus window
    target_y: float = 0.5
    target_x_px: float = 0.0  # stimulus-window pixels
    target_y_px: float = 0.0

    fixation_visible: bool = False
    fixation_x: float = 0.5  # normalized [0, 1] in stimulus window
    fixation_y: float = 0.5


# ---------------------------------------------------------------------------
# Trial-level records (one row per completed trial in trials.csv)
# ---------------------------------------------------------------------------

@dataclass
class TrialRecord:
    """Base record for a single completed trial."""
    session_id: str
    task_id: str
    trial_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trial_number: int = 0
    condition: TrialCondition = TrialCondition.NONE

    # Timing (seconds, relative to session start)
    fixation_onset_sec: float = 0.0
    target_onset_sec: float = 0.0
    trial_end_sec: float = 0.0

    # Response
    response_detected: bool = False
    response_onset_sec: float = 0.0    # 0 if no response
    response_latency_ms: float = 0.0   # 0 if no response

    # Saccade kinematics at response
    response_direction: SaccadeDirection = SaccadeDirection.NONE
    response_velocity_px_per_sec: float = 0.0
    response_amplitude_px: float = 0.0

    # Target geometry
    target_x: float = 0.5    # normalized position
    target_y: float = 0.5
    target_direction: SaccadeDirection = SaccadeDirection.NONE


@dataclass
class SaccadeTrialRecord(TrialRecord):
    """
    One trial from pro-saccade, anti-saccade, or gap-overlap task.

    direction_correct:
      • ProSaccade:  response_direction == target_direction
      • AntiSaccade: response_direction != target_direction (opposite)
      • GapOverlap:  response_direction == target_direction
    """
    direction_correct: bool = False
    # AntiSaccade only: was there a reflexive saccade TOWARD the target
    # (an error that was then corrected, or an uncorrected error)?
    error_saccade_detected: bool = False
    correction_made: bool = False


@dataclass
class PursuitTrialRecord(TrialRecord):
    """
    One cycle of a smooth pursuit trial.

    A "trial" for smooth pursuit is one complete oscillation cycle.
    pursuit_gain = mean(|gaze_velocity|) / mean(|target_velocity|)
    A value near 1.0 indicates accurate tracking.
    """
    cycle_number: int = 0
    # Target kinematics during this cycle
    target_peak_velocity_px_per_sec: float = 0.0
    # Gaze metrics during this cycle
    mean_pursuit_gain: float = 0.0      # gaze_vel / target_vel; ideally ~1.0
    mean_position_error_px: float = 0.0  # mean |gaze - target| in pixels
    time_on_target_ratio: float = 0.0   # fraction of cycle within ±40px of target
    catch_up_saccade_count: int = 0     # large velocity spikes during pursuit


# ---------------------------------------------------------------------------
# Complete task session (returned by TaskRunner.run())
# ---------------------------------------------------------------------------

@dataclass
class TaskSession:
    """
    Everything produced by a single task run.

    Saved by export_task.export_task_session().
    """
    session_id: str
    task_id: str
    task_type: str                      # "prosaccade" | "antisaccade" | etc.
    subject_id: str
    timestamp_start: float
    timestamp_end: float
    software_version: str
    task_config_snapshot: dict          # copy of TaskConfig as dict

    # Data
    task_frames: List[TaskContext] = field(default_factory=list)
    trials: List[TrialRecord]     = field(default_factory=list)

    # Analysis results (filled in after session by task_analysis)
    analysis: dict = field(default_factory=dict)

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.timestamp_end - self.timestamp_start)

    @property
    def num_completed_trials(self) -> int:
        return len(self.trials)
