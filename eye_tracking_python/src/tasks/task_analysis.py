"""
Post-session analysis for structured task protocols — v0.3.

All functions take a list of completed TrialRecord objects and return a plain
dict of summary statistics.  They are called by export_task after the session
ends; nothing here runs in real time.

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

from statistics import mean, stdev
from typing import Any, Dict, List, Optional

from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    SaccadeTrialRecord,
    TrialCondition,
    TrialRecord,
)


# ---------------------------------------------------------------------------
# Pro-saccade analysis
# ---------------------------------------------------------------------------

def analyze_prosaccade(trials: List[TrialRecord]) -> Dict[str, Any]:
    """
    Parameters
    ----------
    trials : completed SaccadeTrialRecord list from ProSaccadeTask

    Returns
    -------
    dict with:
      total_trials, response_rate, mean_latency_ms, sd_latency_ms,
      direction_accuracy, mean_peak_velocity, left/right breakdown
    """
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"error": "no_trials"}

    responded  = [t for t in s_trials if t.response_detected]
    correct    = [t for t in responded if t.direction_correct]
    latencies  = [t.response_latency_ms for t in correct]
    velocities = [t.response_velocity_px_per_sec for t in responded if t.response_velocity_px_per_sec > 0]

    # Directional breakdown
    left_correct  = sum(1 for t in correct if t.target_direction == SaccadeDirection.LEFT)
    right_correct = sum(1 for t in correct if t.target_direction == SaccadeDirection.RIGHT)
    left_total    = sum(1 for t in s_trials if t.target_direction == SaccadeDirection.LEFT)
    right_total   = sum(1 for t in s_trials if t.target_direction == SaccadeDirection.RIGHT)

    result = {
        "task_type": "prosaccade",
        "total_trials": len(s_trials),
        "response_count": len(responded),
        "response_rate": _safe_ratio(len(responded), len(s_trials)),
        "correct_count": len(correct),
        "direction_accuracy": _safe_ratio(len(correct), len(responded)),
        "mean_latency_ms": _safe_mean(latencies),
        "sd_latency_ms": _safe_std(latencies),
        "min_latency_ms": min(latencies) if latencies else 0.0,
        "max_latency_ms": max(latencies) if latencies else 0.0,
        "mean_peak_velocity_px_per_sec": _safe_mean(velocities),
        "left_accuracy": _safe_ratio(left_correct, left_total),
        "right_accuracy": _safe_ratio(right_correct, right_total),
        "disclaimer": _DISCLAIMER,
    }
    return result


# ---------------------------------------------------------------------------
# Anti-saccade analysis
# ---------------------------------------------------------------------------

def analyze_antisaccade(trials: List[TrialRecord]) -> Dict[str, Any]:
    """
    Key metric additions over pro-saccade:
      error_rate           — proportion of trials with a reflexive (toward target) saccade
      correction_rate      — of error trials, proportion that self-corrected
      correct_latency_ms   — latency on correct (anti-saccade) trials
      error_latency_ms     — latency on error (pro-saccade) trials
    """
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"error": "no_trials"}

    responded   = [t for t in s_trials if t.response_detected]
    errors      = [t for t in responded if t.error_saccade_detected]
    corrections = [t for t in errors if t.correction_made]
    correct     = [t for t in responded if t.direction_correct]

    correct_lats = [t.response_latency_ms for t in correct]
    error_lats   = [t.response_latency_ms for t in errors]

    return {
        "task_type": "antisaccade",
        "total_trials": len(s_trials),
        "response_count": len(responded),
        "response_rate": _safe_ratio(len(responded), len(s_trials)),
        "correct_count": len(correct),
        "direction_accuracy": _safe_ratio(len(correct), len(responded)),
        "error_count": len(errors),
        "error_rate": _safe_ratio(len(errors), len(responded)),
        "correction_count": len(corrections),
        "correction_rate": _safe_ratio(len(corrections), len(errors)),
        "mean_correct_latency_ms": _safe_mean(correct_lats),
        "sd_correct_latency_ms": _safe_std(correct_lats),
        "mean_error_latency_ms": _safe_mean(error_lats),
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Gap-overlap analysis
# ---------------------------------------------------------------------------

def analyze_gap_overlap(trials: List[TrialRecord]) -> Dict[str, Any]:
    """
    Key analysis:
      gap_latency_ms     — mean latency on GAP trials
      overlap_latency_ms — mean latency on OVERLAP trials
      gap_effect_ms      — gap_latency - overlap_latency
                           (negative = gap trials faster, expected for healthy adults)
    """
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"error": "no_trials"}

    gap_responded     = [t for t in s_trials
                         if t.condition == TrialCondition.GAP and t.response_detected]
    overlap_responded = [t for t in s_trials
                         if t.condition == TrialCondition.OVERLAP and t.response_detected]

    gap_lats     = [t.response_latency_ms for t in gap_responded if t.direction_correct]
    overlap_lats = [t.response_latency_ms for t in overlap_responded if t.direction_correct]

    mean_gap     = _safe_mean(gap_lats)
    mean_overlap = _safe_mean(overlap_lats)
    gap_effect   = (mean_gap - mean_overlap) if (gap_lats and overlap_lats) else 0.0

    gap_total     = sum(1 for t in s_trials if t.condition == TrialCondition.GAP)
    overlap_total = sum(1 for t in s_trials if t.condition == TrialCondition.OVERLAP)

    return {
        "task_type": "gap_overlap",
        "total_trials": len(s_trials),
        "gap_trials": gap_total,
        "overlap_trials": overlap_total,
        "gap_response_rate": _safe_ratio(len(gap_responded), gap_total),
        "overlap_response_rate": _safe_ratio(len(overlap_responded), overlap_total),
        "mean_gap_latency_ms": mean_gap,
        "sd_gap_latency_ms": _safe_std(gap_lats),
        "mean_overlap_latency_ms": mean_overlap,
        "sd_overlap_latency_ms": _safe_std(overlap_lats),
        "gap_effect_ms": round(gap_effect, 2),
        "gap_accuracy": _safe_ratio(
            sum(1 for t in gap_responded if t.direction_correct), len(gap_responded)
        ),
        "overlap_accuracy": _safe_ratio(
            sum(1 for t in overlap_responded if t.direction_correct), len(overlap_responded)
        ),
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Smooth pursuit analysis
# ---------------------------------------------------------------------------

def analyze_smooth_pursuit(trials: List[TrialRecord]) -> Dict[str, Any]:
    """
    Aggregate pursuit metrics across all completed cycles.

    mean_pursuit_gain near 1.0 indicates accurate velocity tracking.
    Values < 1.0 suggest lagging (undershoot); > 1.0 suggest overshoot.
    """
    p_trials = [t for t in trials if isinstance(t, PursuitTrialRecord)]
    if not p_trials:
        return {"error": "no_cycles"}

    gains     = [t.mean_pursuit_gain for t in p_trials]
    errors_px = [t.mean_position_error_px for t in p_trials]
    on_target = [t.time_on_target_ratio for t in p_trials]
    saccades  = [t.catch_up_saccade_count for t in p_trials]

    return {
        "task_type": "smooth_pursuit",
        "total_cycles": len(p_trials),
        "mean_pursuit_gain": _safe_mean(gains),
        "sd_pursuit_gain": _safe_std(gains),
        "mean_position_error_px": _safe_mean(errors_px),
        "mean_time_on_target": _safe_mean(on_target),
        "total_catch_up_saccades": sum(saccades),
        "mean_catch_up_saccades_per_cycle": _safe_mean(saccades),
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------

def analyze_session(task_type: str, trials: List[TrialRecord]) -> Dict[str, Any]:
    """Route to the appropriate analysis function by task type string."""
    _ANALYZERS = {
        "prosaccade":  analyze_prosaccade,
        "antisaccade": analyze_antisaccade,
        "gap_overlap": analyze_gap_overlap,
        "smooth_pursuit": analyze_smooth_pursuit,
    }
    fn = _ANALYZERS.get(task_type)
    if fn is None:
        return {"error": f"unknown task_type: {task_type}"}
    return fn(trials)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_mean(values: List[float]) -> float:
    return round(mean(values), 3) if values else 0.0


def _safe_std(values: List[float]) -> float:
    return round(stdev(values), 3) if len(values) >= 2 else 0.0


def _safe_ratio(num: int, denom: int) -> float:
    return round(num / denom, 3) if denom else 0.0


_DISCLAIMER = (
    "This software is a research prototype for eye-tracking data collection. "
    "It does not diagnose, treat, predict, or screen for Parkinson's disease or any "
    "other medical condition. Clinical use would require validation, regulatory "
    "review, and healthcare professional oversight."
)
