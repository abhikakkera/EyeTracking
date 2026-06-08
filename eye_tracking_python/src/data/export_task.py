"""
Task-specific export — v0.3.

Writes three files per task session:

  <sid>_task_frames.csv
      One row per frame.  Columns: task context (stimulus state, trial id,
      phase, target position, fixation visibility).
      Join to <sid>_frames.csv on frame_number.

  <sid>_trials.csv
      One row per completed trial.  Columns depend on task type:
        SaccadeTrialRecord  → latency, direction, correct, error flags
        PursuitTrialRecord  → gain, error, on-target ratio, saccade count

  <sid>_task_metadata.json
      Task configuration snapshot, analysis summary, and session metadata.

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import List

from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeTrialRecord,
    TaskSession,
    TrialRecord,
)

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "This software is a research prototype for eye-tracking data collection. "
    "It does not diagnose, treat, predict, or screen for Parkinson's disease or any "
    "other medical condition. Clinical use would require validation, regulatory "
    "review, and healthcare professional oversight."
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_task_session(
    task_session: TaskSession,
    output_dir: str | Path,
) -> List[Path]:
    """
    Write task_frames.csv, trials.csv, and task_metadata.json.

    Parameters
    ----------
    task_session : completed TaskSession from TaskRunner.run()
    output_dir   : directory to write files into

    Returns
    -------
    List of Path objects that were written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sid = task_session.session_id

    written: List[Path] = []
    written.append(_write_task_frames(task_session, out / f"{sid}_task_frames.csv"))
    written.append(_write_trials(task_session, out / f"{sid}_trials.csv"))
    written.append(_write_task_metadata(task_session, out / f"{sid}_task_metadata.json"))

    logger.info(
        "Task export complete: %d frames, %d trials → %s",
        len(task_session.task_frames),
        len(task_session.trials),
        out,
    )
    return written


# ---------------------------------------------------------------------------
# task_frames.csv
# ---------------------------------------------------------------------------

_TASK_FRAME_FIELDS = [
    "session_id", "task_id", "frame_number", "timestamp_sec",
    "trial_number", "trial_id", "task_phase",
    "target_visible", "target_x", "target_y", "target_x_px", "target_y_px",
    "fixation_visible", "fixation_x", "fixation_y",
]


def _write_task_frames(session: TaskSession, path: Path) -> Path:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_TASK_FRAME_FIELDS)
        writer.writeheader()
        for ctx in session.task_frames:
            writer.writerow({
                "session_id":      ctx.session_id,
                "task_id":         ctx.task_id,
                "frame_number":    ctx.frame_number,
                "timestamp_sec":   round(ctx.timestamp_sec, 4),
                "trial_number":    ctx.trial_number,
                "trial_id":        ctx.trial_id,
                "task_phase":      ctx.task_phase.value,
                "target_visible":  int(ctx.target_visible),
                "target_x":        round(ctx.target_x, 4),
                "target_y":        round(ctx.target_y, 4),
                "target_x_px":     round(ctx.target_x_px, 1),
                "target_y_px":     round(ctx.target_y_px, 1),
                "fixation_visible": int(ctx.fixation_visible),
                "fixation_x":      round(ctx.fixation_x, 4),
                "fixation_y":      round(ctx.fixation_y, 4),
            })
    return path


# ---------------------------------------------------------------------------
# trials.csv
# ---------------------------------------------------------------------------

_SACCADE_TRIAL_FIELDS = [
    "session_id", "task_id", "trial_id", "trial_number", "condition",
    "fixation_onset_sec", "target_onset_sec", "trial_end_sec",
    "response_detected", "response_onset_sec", "response_latency_ms",
    "response_direction", "response_velocity_px_per_sec", "response_amplitude_px",
    "target_x", "target_y", "target_direction",
    "direction_correct", "error_saccade_detected", "correction_made",
]

_PURSUIT_TRIAL_FIELDS = [
    "session_id", "task_id", "trial_id", "trial_number", "cycle_number",
    "target_onset_sec", "trial_end_sec",
    "target_peak_velocity_px_per_sec",
    "mean_pursuit_gain", "mean_position_error_px",
    "time_on_target_ratio", "catch_up_saccade_count",
]


def _write_trials(session: TaskSession, path: Path) -> Path:
    trials = session.trials
    if not trials:
        # Write an empty file so the path always exists
        path.write_text("")
        return path

    if isinstance(trials[0], SaccadeTrialRecord):
        fields = _SACCADE_TRIAL_FIELDS
        rows   = [_saccade_row(t) for t in trials]
    elif isinstance(trials[0], PursuitTrialRecord):
        fields = _PURSUIT_TRIAL_FIELDS
        rows   = [_pursuit_row(t) for t in trials]
    else:
        # Generic fallback — write whatever attributes exist
        fields = list(vars(trials[0]).keys())
        rows   = [vars(t) for t in trials]

    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _saccade_row(t: SaccadeTrialRecord) -> dict:
    return {
        "session_id":                  t.session_id,
        "task_id":                     t.task_id,
        "trial_id":                    t.trial_id,
        "trial_number":                t.trial_number,
        "condition":                   t.condition.value,
        "fixation_onset_sec":          round(t.fixation_onset_sec, 4),
        "target_onset_sec":            round(t.target_onset_sec, 4),
        "trial_end_sec":               round(t.trial_end_sec, 4),
        "response_detected":           int(t.response_detected),
        "response_onset_sec":          round(t.response_onset_sec, 4),
        "response_latency_ms":         round(t.response_latency_ms, 2),
        "response_direction":          t.response_direction.value,
        "response_velocity_px_per_sec": round(t.response_velocity_px_per_sec, 2),
        "response_amplitude_px":       round(t.response_amplitude_px, 2),
        "target_x":                    round(t.target_x, 4),
        "target_y":                    round(t.target_y, 4),
        "target_direction":            t.target_direction.value,
        "direction_correct":           int(t.direction_correct),
        "error_saccade_detected":      int(t.error_saccade_detected),
        "correction_made":             int(t.correction_made),
    }


def _pursuit_row(t: PursuitTrialRecord) -> dict:
    return {
        "session_id":                      t.session_id,
        "task_id":                         t.task_id,
        "trial_id":                        t.trial_id,
        "trial_number":                    t.trial_number,
        "cycle_number":                    t.cycle_number,
        "target_onset_sec":                round(t.target_onset_sec, 4),
        "trial_end_sec":                   round(t.trial_end_sec, 4),
        "target_peak_velocity_px_per_sec": round(t.target_peak_velocity_px_per_sec, 2),
        "mean_pursuit_gain":               round(t.mean_pursuit_gain, 3),
        "mean_position_error_px":          round(t.mean_position_error_px, 2),
        "time_on_target_ratio":            round(t.time_on_target_ratio, 3),
        "catch_up_saccade_count":          t.catch_up_saccade_count,
    }


# ---------------------------------------------------------------------------
# task_metadata.json
# ---------------------------------------------------------------------------

def _write_task_metadata(session: TaskSession, path: Path) -> Path:
    doc = {
        "session_id":       session.session_id,
        "task_id":          session.task_id,
        "task_type":        session.task_type,
        "subject_id":       session.subject_id,
        "software_version": session.software_version,
        "timestamp_start":  session.timestamp_start,
        "timestamp_end":    session.timestamp_end,
        "duration_sec":     round(session.duration_sec, 2),
        "num_completed_trials": session.num_completed_trials,
        "task_config":      session.task_config_snapshot,
        "analysis":         session.analysis,
        "disclaimer":       _DISCLAIMER,
    }
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, default=str)
    return path
