"""
Task event recorder + trial reconstruction for web task mode.

The browser owns the stimulus timeline and emits structural events
(task_started, trial_started, target_shown, trial_ended, ...). The backend
stores one WebFrame per streamed frame (task context + tracker gaze).

On completion this module reconstructs the SAME trial dataclasses the CLI tasks
produced (SaccadeTrialRecord / PursuitTrialRecord), so the existing
src.tasks.task_analysis + export + result_parser all work unchanged.

No medical interpretation — task performance + tracking quality only.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeDirection,
    SaccadeTrialRecord,
    TaskContext,
    TaskPhase,
    TrialCondition,
    TrialRecord,
)

logger = logging.getLogger(__name__)

_ON_TARGET_PX = 80.0
_CATCHUP_RATIO = 3.0


@dataclass
class WebFrame:
    """One streamed frame: task context (from browser) + gaze (from tracker)."""
    frame_number: int = 0
    browser_ts_ms: float = 0.0
    server_ts_sec: float = 0.0

    # Task context (sent by the browser with the frame)
    trial_id: str = ""
    trial_number: int = -1
    task_phase: str = "waiting"
    target_visible: bool = False
    target_x: float = 0.5
    target_y: float = 0.5
    target_direction: str = "none"
    condition: str = "none"
    fixation_visible: bool = False

    # Tracker output
    gaze_x: float = 0.5
    gaze_y: float = 0.5
    face_detected: bool = False
    blink: bool = False
    confidence: float = 0.0
    frame_quality: str = "bad"
    distance_status: str = "unknown"
    velocity_px_s: float = 0.0


# ---------------------------------------------------------------------------
# Direction / condition mapping
# ---------------------------------------------------------------------------

def _dir(s: Optional[str]) -> SaccadeDirection:
    if s == "left":
        return SaccadeDirection.LEFT
    if s == "right":
        return SaccadeDirection.RIGHT
    return SaccadeDirection.NONE


def _cond(s: Optional[str]) -> TrialCondition:
    if s == "gap":
        return TrialCondition.GAP
    if s == "overlap":
        return TrialCondition.OVERLAP
    return TrialCondition.NONE


def _phase(s: str) -> TaskPhase:
    try:
        return TaskPhase(s)
    except ValueError:
        return TaskPhase.WAITING


# ---------------------------------------------------------------------------
# Public: build TaskContext list (for task_frames.csv export)
# ---------------------------------------------------------------------------

def build_task_contexts(
    session_id: str, task_id: str, frames: List[WebFrame], screen_w: int, screen_h: int,
) -> List[TaskContext]:
    out: List[TaskContext] = []
    for f in frames:
        out.append(TaskContext(
            session_id=session_id,
            task_id=task_id,
            frame_number=f.frame_number,
            timestamp_sec=f.server_ts_sec,
            trial_number=f.trial_number,
            trial_id=f.trial_id,
            task_phase=_phase(f.task_phase),
            target_visible=f.target_visible,
            target_x=f.target_x,
            target_y=f.target_y,
            target_x_px=f.target_x * screen_w,
            target_y_px=f.target_y * screen_h,
            fixation_visible=f.fixation_visible,
            fixation_x=0.5,
            fixation_y=0.5,
        ))
    return out


# ---------------------------------------------------------------------------
# Public: reconstruct trials
# ---------------------------------------------------------------------------

def reconstruct_trials(
    task_type: str,
    session_id: str,
    task_id: str,
    frames: List[WebFrame],
    events: List[dict],
    response_threshold: float,
    screen_w: int,
    screen_h: int,
) -> List[TrialRecord]:
    if task_type == "smooth_pursuit":
        return _reconstruct_pursuit(session_id, task_id, frames, events, screen_w, screen_h)
    return _reconstruct_saccade(task_type, session_id, task_id, frames, events, response_threshold)


# ---------------------------------------------------------------------------
# Saccade-family reconstruction (pro / anti / gap-overlap)
# ---------------------------------------------------------------------------

def _reconstruct_saccade(
    task_type: str,
    session_id: str,
    task_id: str,
    frames: List[WebFrame],
    events: List[dict],
    thr: float,
) -> List[TrialRecord]:
    trials: List[TrialRecord] = []
    by_tid: Dict[str, List[WebFrame]] = {}
    for f in frames:
        by_tid.setdefault(f.trial_id, []).append(f)

    for ev in [e for e in events if e.get("type") == "trial_started"]:
        tid = ev.get("trial_id") or ""
        tnum = int(ev.get("trial_number") or 0)
        target_dir = _dir(ev.get("direction"))
        condition = _cond(ev.get("condition"))

        target_ev = _find(events, "target_shown", tid)
        fix_ev = _find(events, "fixation_shown", tid)
        end_ev = _find(events, "trial_ended", tid)

        onset_ms = target_ev["timestamp_ms"] if target_ev else ev["timestamp_ms"]
        fix_ms = fix_ev["timestamp_ms"] if fix_ev else ev["timestamp_ms"]
        end_ms = end_ev["timestamp_ms"] if end_ev else onset_ms

        tframes = sorted(by_tid.get(tid, []), key=lambda f: f.browser_ts_ms)
        pre = [f.gaze_x for f in tframes if f.browser_ts_ms < onset_ms and f.face_detected]
        baseline = sum(pre) / len(pre) if pre else 0.5

        response = None
        for f in tframes:
            if f.browser_ts_ms < onset_ms:
                continue
            if not f.face_detected or f.blink:
                continue
            if abs(f.gaze_x - baseline) > thr:
                response = f
                break

        rec = SaccadeTrialRecord(
            session_id=session_id,
            task_id=task_id,
            trial_id=tid,
            trial_number=tnum,
            condition=condition,
            fixation_onset_sec=fix_ms / 1000.0,
            target_onset_sec=onset_ms / 1000.0,
            trial_end_sec=end_ms / 1000.0,
            target_x=target_ev.get("target_x", 0.5) if target_ev else 0.5,
            target_y=target_ev.get("target_y", 0.5) if target_ev else 0.5,
            target_direction=target_dir,
        )

        if response is not None:
            resp_dir = (
                SaccadeDirection.RIGHT if (response.gaze_x - baseline) > 0
                else SaccadeDirection.LEFT
            )
            rec.response_detected = True
            rec.response_onset_sec = response.browser_ts_ms / 1000.0
            rec.response_latency_ms = max(0.0, response.browser_ts_ms - onset_ms)
            rec.response_direction = resp_dir
            rec.response_velocity_px_per_sec = response.velocity_px_s

            toward_target = resp_dir == target_dir
            if task_type == "antisaccade":
                rec.direction_correct = not toward_target
                rec.error_saccade_detected = toward_target
                if toward_target:
                    rec.correction_made = _has_correction(
                        tframes, response.browser_ts_ms, baseline, target_dir, thr
                    )
            else:
                rec.direction_correct = toward_target

        trials.append(rec)

    return trials


def _has_correction(tframes, after_ms, baseline, target_dir, thr) -> bool:
    """After a reflexive error toward the target, did gaze move to the opposite side?"""
    for f in tframes:
        if f.browser_ts_ms <= after_ms or not f.face_detected:
            continue
        disp = f.gaze_x - baseline
        moved_dir = SaccadeDirection.RIGHT if disp > 0 else SaccadeDirection.LEFT
        if abs(disp) > thr and moved_dir != target_dir:
            return True
    return False


# ---------------------------------------------------------------------------
# Smooth pursuit reconstruction (one PursuitTrialRecord per cycle)
# ---------------------------------------------------------------------------

def _reconstruct_pursuit(
    session_id: str,
    task_id: str,
    frames: List[WebFrame],
    events: List[dict],
    screen_w: int,
    screen_h: int,
) -> List[TrialRecord]:
    trials: List[TrialRecord] = []
    by_tid: Dict[str, List[WebFrame]] = {}
    for f in frames:
        by_tid.setdefault(f.trial_id, []).append(f)

    for ev in [e for e in events if e.get("type") == "trial_started"]:
        tid = ev.get("trial_id") or ""
        cyc = int(ev.get("cycle_number") or ev.get("trial_number") or 0)
        end_ev = _find(events, "trial_ended", tid)

        tframes = sorted(
            [f for f in by_tid.get(tid, []) if f.face_detected and not f.blink],
            key=lambda f: f.browser_ts_ms,
        )

        gaze_speeds: List[float] = []
        target_speeds: List[float] = []
        catch_up = 0
        for a, b in zip(tframes, tframes[1:]):
            dt = (b.browser_ts_ms - a.browser_ts_ms) / 1000.0
            if dt <= 0:
                continue
            gs = math.hypot((b.gaze_x - a.gaze_x) * screen_w, (b.gaze_y - a.gaze_y) * screen_h) / dt
            tsp = math.hypot((b.target_x - a.target_x) * screen_w, (b.target_y - a.target_y) * screen_h) / dt
            gaze_speeds.append(gs)
            target_speeds.append(tsp)
            if tsp > 10 and gs > _CATCHUP_RATIO * tsp:
                catch_up += 1

        errs = [
            math.hypot((f.gaze_x - f.target_x) * screen_w, (f.gaze_y - f.target_y) * screen_h)
            for f in tframes
        ]
        mean_target = (sum(target_speeds) / len(target_speeds)) if target_speeds else 0.0
        mean_gaze = (sum(gaze_speeds) / len(gaze_speeds)) if gaze_speeds else 0.0
        gain = (mean_gaze / mean_target) if mean_target > 0 else 0.0
        on_ratio = (sum(1 for e in errs if e < _ON_TARGET_PX) / len(errs)) if errs else 0.0

        start_ms = ev["timestamp_ms"]
        end_ms = end_ev["timestamp_ms"] if end_ev else start_ms

        trials.append(PursuitTrialRecord(
            session_id=session_id,
            task_id=task_id,
            trial_id=tid,
            trial_number=cyc,
            condition=TrialCondition.NONE,
            target_onset_sec=start_ms / 1000.0,
            trial_end_sec=end_ms / 1000.0,
            response_detected=True,
            cycle_number=cyc,
            target_peak_velocity_px_per_sec=round(max(target_speeds), 2) if target_speeds else 0.0,
            mean_pursuit_gain=round(max(0.0, gain), 3),
            mean_position_error_px=round(sum(errs) / len(errs), 2) if errs else 0.0,
            time_on_target_ratio=round(on_ratio, 3),
            catch_up_saccade_count=catch_up,
        ))

    return trials


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find(events: List[dict], etype: str, trial_id: str) -> Optional[dict]:
    for e in events:
        if e.get("type") == etype and e.get("trial_id") == trial_id:
            return e
    return None
