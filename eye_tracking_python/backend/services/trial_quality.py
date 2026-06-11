"""
Trial-quality engine for Ocula web sessions.

The reported bug: a session with 93% usable frames and only 26/597 no-face frames
was showing "main unclear reason: no_face" with 6/12 unclear trials. Two separate
ideas were conflated:

  • whether a ROUND could be tracked (a tracking-quality question), and
  • whether the participant produced a saccadic RESPONSE (a task question).

This module answers the first one honestly and per-trial, using the response
WINDOW (not the whole recording), with tolerance for a few missing frames and
short face-detection dropouts. It also produces accurate, trial-level reasons so
"no_face" is only blamed when missing faces actually broke a round.

It consumes the in-memory WebFrame list (which carries both the browser task
context AND the tracker output) plus the reconstructed trials, and returns a
diagnostics bundle for result_parser / the developer panel.

Raw frames are untouched — this only shapes PROCESSED metrics.
No medical interpretation: tracking quality + task performance only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Phases that count as real task recording (vs setup/countdown/between-trials).
TASK_PHASE = "task"

# Task sub-phases (from the browser stimulus timeline).
_RESPONSE_PHASES = ("target",)
_TRIAL_PHASES = ("fixation", "gap", "target")


@dataclass
class _Frame:
    """Minimal view of a streamed frame for quality math (duck-typed from WebFrame)."""
    browser_ts_ms: float
    trial_id: str
    task_phase: str
    recording_phase: str
    face_detected: bool
    blink: bool
    confidence: float
    frame_quality: str


def _as_frame(f: Any) -> _Frame:
    return _Frame(
        browser_ts_ms=float(getattr(f, "browser_ts_ms", 0.0) or 0.0),
        trial_id=str(getattr(f, "trial_id", "") or ""),
        task_phase=str(getattr(f, "task_phase", "waiting") or "waiting"),
        recording_phase=str(getattr(f, "recording_phase", "") or _infer_phase(f)),
        face_detected=bool(getattr(f, "face_detected", False)),
        blink=bool(getattr(f, "blink", False)),
        confidence=float(getattr(f, "confidence", 0.0) or 0.0),
        frame_quality=str(getattr(f, "frame_quality", "bad") or "bad"),
    )


def _infer_phase(f: Any) -> str:
    """Fallback recording_phase if the browser didn't tag one (older clients)."""
    tp = str(getattr(f, "task_phase", "waiting") or "waiting")
    if tp in _TRIAL_PHASES:
        return "task"
    if tp == "iti":
        return "between_trials"
    if tp == "done":
        return "complete"
    return "setup"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(
    task_type: str,
    web_frames: Sequence[Any],
    trials: Sequence[Any],
    cfg: Any,
) -> Dict[str, Any]:
    """
    Returns a diagnostics dict:

        {
          "per_trial": [ {...full trial debug row...} ],
          "counts": {"clear", "unclear", "bad", "total"},
          "well_tracked_trials": int,        # clear
          "untrackable_trials": int,         # unclear + bad
          "rounds_with_response": int,       # response_detected
          "main_unclear_reason": str|None,   # trial-level, None when all clear
          "no_face": {...timing diagnostics...},
          "frame_stats": {...TASK-phase-only counts + usable%...},
        }
    """
    frames = [_as_frame(f) for f in web_frames]
    usable_conf = float(getattr(cfg, "usable_confidence_threshold", 0.40))
    clear_min = float(getattr(cfg, "trial_clear_min_usable_percent", 70.0))
    rw_min = float(getattr(cfg, "trial_response_window_min_percent", 60.0))
    bad_max = float(getattr(cfg, "trial_bad_max_usable_percent", 40.0))
    dropout_ms = float(getattr(cfg, "short_dropout_max_ms", 200))
    onset_guard_ms = float(getattr(cfg, "target_onset_guard_ms", 150))

    by_tid: Dict[str, List[_Frame]] = {}
    for f in frames:
        by_tid.setdefault(f.trial_id, []).append(f)
    for lst in by_tid.values():
        lst.sort(key=lambda f: f.browser_ts_ms)

    per_trial: List[Dict[str, Any]] = []
    counts = Counter()
    unclear_reasons: Counter = Counter()

    for t in trials:
        row = _judge_trial(
            t, by_tid.get(str(getattr(t, "trial_id", "") or ""), []),
            usable_conf, clear_min, rw_min, bad_max, dropout_ms, onset_guard_ms,
        )
        per_trial.append(row)
        counts[row["trial_quality"]] += 1
        if row["trial_quality"] != "clear" and row["unclear_reason"]:
            unclear_reasons[row["unclear_reason"]] += 1

    clear = counts.get("clear", 0)
    unclear = counts.get("unclear", 0)
    bad = counts.get("bad", 0)
    responded = sum(1 for t in trials if bool(getattr(t, "response_detected", False)))

    return {
        "per_trial": per_trial,
        "counts": {"clear": clear, "unclear": unclear, "bad": bad, "total": len(per_trial)},
        "well_tracked_trials": clear,
        "untrackable_trials": unclear + bad,
        "rounds_with_response": responded,
        "main_unclear_reason": unclear_reasons.most_common(1)[0][0] if unclear_reasons else None,
        "no_face": _no_face_diagnostics(frames, per_trial, usable_conf),
        "frame_stats": _task_frame_stats(frames, usable_conf),
    }


# ---------------------------------------------------------------------------
# Per-trial judgement
# ---------------------------------------------------------------------------

def _usable(f: _Frame, conf: float) -> bool:
    return (
        f.face_detected
        and not f.blink
        and f.frame_quality != "bad"
        and f.confidence >= conf
    )


def _judge_trial(
    trial: Any,
    frames: List[_Frame],
    usable_conf: float,
    clear_min: float,
    rw_min: float,
    bad_max: float,
    dropout_ms: float,
    onset_guard_ms: float,
) -> Dict[str, Any]:
    tid = str(getattr(trial, "trial_id", "") or "")
    tnum = getattr(trial, "trial_number", None)
    direction = _direction_str(getattr(trial, "target_direction", None))
    responded = bool(getattr(trial, "response_detected", False))
    rt_ms = getattr(trial, "response_latency_ms", None)
    rt_ms = round(float(rt_ms), 1) if responded and rt_ms else None

    # Trial-proper frames (fixation/gap/target) — excludes the inter-trial tail.
    proper = [f for f in frames if f.task_phase in _TRIAL_PHASES]
    rw = [f for f in frames if f.task_phase in _RESPONSE_PHASES]

    total = len(proper)
    usable_n = sum(1 for f in proper if _usable(f, usable_conf))
    no_face_n = sum(1 for f in proper if not f.face_detected)
    blink_n = sum(1 for f in proper if f.blink)

    rw_total = len(rw)
    rw_usable = sum(1 for f in rw if _usable(f, usable_conf))
    rw_no_face = sum(1 for f in rw if not f.face_detected)
    rw_blink = sum(1 for f in rw if f.blink)

    usable_pct = round(100.0 * usable_n / total, 1) if total else 0.0
    rw_pct = round(100.0 * rw_usable / rw_total, 1) if rw_total else 0.0

    onset_ms = rw[0].browser_ts_ms if rw else None
    near_onset = (
        [f for f in rw if onset_ms is not None and f.browser_ts_ms <= onset_ms + onset_guard_ms]
        if onset_ms is not None else []
    )
    no_face_at_onset = any(not f.face_detected for f in near_onset)
    no_face_in_rw = rw_no_face > 0

    # Longest contiguous no-face streak inside the response window.
    streak_frames, streak_ms = _longest_no_face_streak(rw or proper)
    short_dropout = _is_short_dropout(rw or proper, usable_conf, dropout_ms)

    flags: List[str] = []
    if short_dropout:
        flags.append("short_face_dropout")

    # ---- Classification (tracking quality of the MEASUREMENT, with grace) ----
    if total == 0:
        quality, reason = "bad", "no_tracking_data"
    elif usable_pct < bad_max:
        quality = "bad"
        reason = "no_face_major" if total and (no_face_n / total) >= 0.5 else "insufficient_tracking"
    elif rw_total == 0:
        quality, reason = "unclear", "insufficient_response_window_data"
    elif rw_pct < rw_min:
        # The decisive window is too sparse — say WHY accurately.
        if no_face_at_onset:
            quality, reason = "unclear", "no_face_at_target_onset"
        elif rw_blink > rw_no_face and rw_blink > 0:
            quality, reason = "unclear", "blink_during_response_window"
        elif rw_no_face > 0:
            quality, reason = "unclear", "no_face_brief_dropout" if short_dropout else "insufficient_response_window_data"
        else:
            quality, reason = "unclear", "insufficient_response_window_data"
    else:
        # Response window adequately tracked → the round is measurable ("clear"),
        # even if a few fixation/setup frames were missing. This is the grace fix.
        quality, reason = "clear", None
        if usable_pct < clear_min:
            flags.append("partial_tracking")
        if not responded:
            # We tracked it well and saw no saccade → a valid "no response" result.
            flags.append("no_gaze_response")

    return {
        "trial_id": tid,
        "trial_number": tnum,
        "target_direction": direction,
        "total_trial_frames": total,
        "usable_trial_frames": usable_n,
        "usable_trial_frame_percent": usable_pct,
        "no_face_frame_count": no_face_n,
        "no_face_frame_percent": round(100.0 * no_face_n / total, 1) if total else 0.0,
        "blink_frame_count": blink_n,
        "response_window_frames": rw_total,
        "usable_response_window_frames": rw_usable,
        "usable_response_window_percent": rw_pct,
        "no_face_near_target_onset": no_face_at_onset,
        "no_face_in_response_window": no_face_in_rw,
        "longest_no_face_streak_frames": streak_frames,
        "longest_no_face_streak_ms": streak_ms,
        "short_dropout": short_dropout,
        "response_detected": responded,
        "reaction_time_ms": rt_ms,
        "trial_quality": quality,
        "unclear_reason": reason,
        "quality_flags": flags,
    }


# ---------------------------------------------------------------------------
# No-face streak helpers
# ---------------------------------------------------------------------------

def _longest_no_face_streak(frames: List[_Frame]) -> tuple[int, float]:
    """Longest run of consecutive no-face frames → (frame_count, duration_ms)."""
    best_n = 0
    best_ms = 0.0
    run: List[_Frame] = []

    def close(run: List[_Frame]) -> None:
        nonlocal best_n, best_ms
        if len(run) > best_n:
            best_n = len(run)
            best_ms = round(run[-1].browser_ts_ms - run[0].browser_ts_ms, 1) if len(run) > 1 else 0.0

    for f in frames:
        if not f.face_detected:
            run.append(f)
        else:
            close(run)
            run = []
    close(run)
    return best_n, best_ms


def _is_short_dropout(frames: List[_Frame], conf: float, dropout_ms: float) -> bool:
    """
    True if every no-face gap is short (≤ dropout_ms) AND bridged by usable frames
    on both sides — i.e. brief, recoverable loss rather than a real interruption.
    """
    found = False
    i = 0
    n = len(frames)
    while i < n:
        if frames[i].face_detected:
            i += 1
            continue
        j = i
        while j < n and not frames[j].face_detected:
            j += 1
        # gap is frames[i..j-1]
        gap = frames[i:j]
        dur = (gap[-1].browser_ts_ms - gap[0].browser_ts_ms) if len(gap) > 1 else 0.0
        before_ok = i > 0 and _usable(frames[i - 1], conf)
        after_ok = j < n and _usable(frames[j], conf)
        if not (before_ok and after_ok and dur <= dropout_ms):
            return False  # an unbridged / long gap exists → not a "short dropout" trial
        found = True
        i = j
    return found


# ---------------------------------------------------------------------------
# Session-level no-face timing diagnostics
# ---------------------------------------------------------------------------

def _no_face_diagnostics(
    frames: List[_Frame], per_trial: List[Dict[str, Any]], conf: float
) -> Dict[str, Any]:
    task_frames = [f for f in frames if f.recording_phase == TASK_PHASE]
    by_phase: Counter = Counter()
    for f in frames:
        if not f.face_detected:
            by_phase[f.recording_phase or "unknown"] += 1

    total_task = len(task_frames)
    no_face_task = sum(1 for f in task_frames if not f.face_detected)
    streak_frames, streak_ms = _longest_no_face_streak(task_frames)

    by_trial = [
        {
            "trial_id": r["trial_id"],
            "trial_number": r["trial_number"],
            "no_face_frames": r["no_face_frame_count"],
            "no_face_near_target_onset": r["no_face_near_target_onset"],
            "no_face_in_response_window": r["no_face_in_response_window"],
            "longest_streak_ms": r["longest_no_face_streak_ms"],
        }
        for r in per_trial
    ]

    return {
        "total_frames": no_face_task,
        "percent": round(100.0 * no_face_task / total_task, 1) if total_task else 0.0,
        "by_phase": dict(by_phase),
        "by_trial": by_trial,
        "longest_streak_frames": streak_frames,
        "longest_streak_ms": streak_ms,
    }


# ---------------------------------------------------------------------------
# Task-phase-only frame stats (the honest usable% denominator)
# ---------------------------------------------------------------------------

def _task_frame_stats(frames: List[_Frame], conf: float) -> Dict[str, Any]:
    task_frames = [f for f in frames if f.recording_phase == TASK_PHASE]
    total = len(task_frames)
    with_face = sum(1 for f in task_frames if f.face_detected)
    usable = sum(1 for f in task_frames if _usable(f, conf))
    gaze = sum(1 for f in task_frames if f.face_detected and not f.blink)
    conf_vals = [f.confidence for f in task_frames if f.face_detected]

    return {
        "total_task_frames": total,
        "frames_with_face_detected": with_face,
        "frames_with_gaze": gaze,
        "usable_eye_tracking_frames": usable,
        "usable_eye_tracking_percent": round(100.0 * usable / total, 1) if total else None,
        "average_confidence": round(sum(conf_vals) / len(conf_vals), 3) if conf_vals else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _direction_str(d: Any) -> str:
    if d is None:
        return "none"
    val = getattr(d, "value", d)
    return str(val)
