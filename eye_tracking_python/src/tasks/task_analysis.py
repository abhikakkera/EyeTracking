"""
Post-session analysis for structured task protocols — v0.3 (v0.5 null-safe).

All functions take a list of completed TrialRecord objects and return a plain
dict of summary statistics.

NULL-vs-ZERO POLICY (v0.5 fix):
  A statistic that has NO valid samples is returned as None, never 0.0.
  Examples: if no trial produced a response, mean_latency_ms is None (not 0.0)
  and direction_accuracy is None (not 0.0).  Counts (response_count, etc.) are
  genuine integers — 0 there means "zero occurred", which is real information.

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
    Pro-saccade ("Look Toward the Dot") summary.

    Latency / velocity / accuracy statistics are None when there are no valid
    responses to compute them from.
    """
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"task_type": "prosaccade", "total_trials": 0, "response_count": 0,
                "error": "no_trials", "disclaimer": _DISCLAIMER}

    responded  = [t for t in s_trials if t.response_detected]
    correct    = [t for t in responded if t.direction_correct]
    latencies  = [t.response_latency_ms for t in correct if t.response_latency_ms > 0]
    velocities = [t.response_velocity_px_per_sec for t in responded if t.response_velocity_px_per_sec > 0]

    return {
        "task_type": "prosaccade",
        "total_trials": len(s_trials),
        "response_count": len(responded),
        "response_rate": _safe_ratio(len(responded), len(s_trials)),
        "correct_count": len(correct),
        "direction_accuracy": _safe_ratio(len(correct), len(responded)),
        "mean_latency_ms": _safe_mean(latencies),
        "sd_latency_ms": _safe_std(latencies),
        "min_latency_ms": _safe_min(latencies),
        "max_latency_ms": _safe_max(latencies),
        "mean_peak_velocity_px_per_sec": _safe_mean(velocities),
        "left_accuracy": _safe_ratio(
            sum(1 for t in correct if t.target_direction == SaccadeDirection.LEFT),
            sum(1 for t in s_trials if t.target_direction == SaccadeDirection.LEFT),
        ),
        "right_accuracy": _safe_ratio(
            sum(1 for t in correct if t.target_direction == SaccadeDirection.RIGHT),
            sum(1 for t in s_trials if t.target_direction == SaccadeDirection.RIGHT),
        ),
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Anti-saccade analysis
# ---------------------------------------------------------------------------

def analyze_antisaccade(trials: List[TrialRecord]) -> Dict[str, Any]:
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"task_type": "antisaccade", "total_trials": 0, "response_count": 0,
                "error": "no_trials", "disclaimer": _DISCLAIMER}

    responded   = [t for t in s_trials if t.response_detected]
    errors      = [t for t in responded if t.error_saccade_detected]
    corrections = [t for t in errors if t.correction_made]
    correct     = [t for t in responded if t.direction_correct]

    correct_lats = [t.response_latency_ms for t in correct if t.response_latency_ms > 0]
    error_lats   = [t.response_latency_ms for t in errors if t.response_latency_ms > 0]

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
    s_trials = [t for t in trials if isinstance(t, SaccadeTrialRecord)]
    if not s_trials:
        return {"task_type": "gap_overlap", "total_trials": 0, "response_count": 0,
                "error": "no_trials", "disclaimer": _DISCLAIMER}

    gap_responded     = [t for t in s_trials
                         if t.condition == TrialCondition.GAP and t.response_detected]
    overlap_responded = [t for t in s_trials
                         if t.condition == TrialCondition.OVERLAP and t.response_detected]

    gap_lats     = [t.response_latency_ms for t in gap_responded
                    if t.direction_correct and t.response_latency_ms > 0]
    overlap_lats = [t.response_latency_ms for t in overlap_responded
                    if t.direction_correct and t.response_latency_ms > 0]

    mean_gap     = _safe_mean(gap_lats)
    mean_overlap = _safe_mean(overlap_lats)
    gap_effect   = round(mean_gap - mean_overlap, 2) if (mean_gap is not None and mean_overlap is not None) else None

    gap_total     = sum(1 for t in s_trials if t.condition == TrialCondition.GAP)
    overlap_total = sum(1 for t in s_trials if t.condition == TrialCondition.OVERLAP)

    return {
        "task_type": "gap_overlap",
        "total_trials": len(s_trials),
        "response_count": len(gap_responded) + len(overlap_responded),
        "gap_trials": gap_total,
        "overlap_trials": overlap_total,
        "gap_response_count": len(gap_responded),
        "overlap_response_count": len(overlap_responded),
        "gap_response_rate": _safe_ratio(len(gap_responded), gap_total),
        "overlap_response_rate": _safe_ratio(len(overlap_responded), overlap_total),
        "mean_gap_latency_ms": mean_gap,
        "sd_gap_latency_ms": _safe_std(gap_lats),
        "mean_overlap_latency_ms": mean_overlap,
        "sd_overlap_latency_ms": _safe_std(overlap_lats),
        "gap_effect_ms": gap_effect,
        "gap_accuracy": _safe_ratio(
            sum(1 for t in gap_responded if t.direction_correct), len(gap_responded)),
        "overlap_accuracy": _safe_ratio(
            sum(1 for t in overlap_responded if t.direction_correct), len(overlap_responded)),
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Smooth pursuit analysis
# ---------------------------------------------------------------------------

def analyze_smooth_pursuit(trials: List[TrialRecord]) -> Dict[str, Any]:
    p_trials = [t for t in trials if isinstance(t, PursuitTrialRecord)]
    if not p_trials:
        return {"task_type": "smooth_pursuit", "total_cycles": 0,
                "valid_cycles": 0, "error": "no_cycles", "disclaimer": _DISCLAIMER}

    # A cycle is "valid" only if it actually had usable gaze samples
    # (gain or position error computed from real frames).
    valid = [t for t in p_trials
             if (t.mean_pursuit_gain or 0) > 0 or (t.mean_position_error_px or 0) > 0]

    gains     = [t.mean_pursuit_gain for t in valid]
    errors_px = [t.mean_position_error_px for t in valid]
    on_target = [t.time_on_target_ratio for t in valid]
    saccades  = [t.catch_up_saccade_count for t in valid]

    return {
        "task_type": "smooth_pursuit",
        "total_cycles": len(p_trials),
        "valid_cycles": len(valid),
        "mean_pursuit_gain": _safe_mean(gains),
        "sd_pursuit_gain": _safe_std(gains),
        "mean_position_error_px": _safe_mean(errors_px),
        "mean_time_on_target": _safe_mean(on_target),
        "total_catch_up_saccades": sum(saccades) if saccades else 0,
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
# Internal helpers — None when there is nothing to measure
# ---------------------------------------------------------------------------

def _safe_mean(values: List[float]) -> Optional[float]:
    return round(mean(values), 3) if values else None


def _safe_std(values: List[float]) -> Optional[float]:
    return round(stdev(values), 3) if len(values) >= 2 else None


def _safe_min(values: List[float]) -> Optional[float]:
    return round(min(values), 3) if values else None


def _safe_max(values: List[float]) -> Optional[float]:
    return round(max(values), 3) if values else None


def _safe_ratio(num: int, denom: int) -> Optional[float]:
    return round(num / denom, 3) if denom else None


_DISCLAIMER = (
    "This software is a research prototype for eye-tracking data collection. "
    "It does not diagnose, treat, predict, or screen for Parkinson's disease or any "
    "other medical condition. Clinical use would require validation, regulatory "
    "review, and healthcare professional oversight."
)
