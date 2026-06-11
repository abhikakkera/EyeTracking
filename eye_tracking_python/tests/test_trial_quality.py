"""
Tests for the trial-quality engine (the no_face / unclear-trial fix).

Covers the scenarios from the bug report:
  A. a short no-face dropout does NOT make a trial unclear
  B. no-face for the whole response window DOES make it unclear (accurate reason)
  C. high usable% + low response rate → "Okay", with trial-level suggestions
  D. setup frames are not counted toward task usable%
  E. countdown frames are not counted toward task usable%
  F. no_face diagnostics are broken down by phase and by trial
  G. a sub-200ms dropout is bridged (continuity kept, confidence flagged)
"""
from __future__ import annotations

from config import CONFIG
from backend.services import trial_quality, result_parser
from backend.services.task_event_recorder import WebFrame


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

class _Trial:
    def __init__(self, trial_id="t1", trial_number=1, response_detected=True,
                 response_latency_ms=220.0, target_direction="left"):
        self.trial_id = trial_id
        self.trial_number = trial_number
        self.response_detected = response_detected
        self.response_latency_ms = response_latency_ms
        self.target_direction = target_direction


def _frames(tid, n, *, no_face=(), blink=(), phase="target", rec="task",
            start_ms=1000.0, dt=66.0, conf=0.8):
    out = []
    no_face = set(no_face)
    blink = set(blink)
    for i in range(n):
        out.append(WebFrame(
            frame_number=i,
            browser_ts_ms=start_ms + i * dt,
            trial_id=tid,
            task_phase=phase,
            recording_phase=rec,
            face_detected=i not in no_face,
            blink=i in blink,
            confidence=conf,
            frame_quality="good",
        ))
    return out


# ---------------------------------------------------------------------------
# A + G — short dropout does not ruin a trial; continuity preserved
# ---------------------------------------------------------------------------

def test_a_short_dropout_keeps_trial_clear():
    frames = _frames("t1", 50, no_face=(24, 25))  # 2 of 50 frames, ~66ms gap
    out = trial_quality.analyze("prosaccade", frames, [_Trial("t1")], CONFIG.web_capture)
    row = out["per_trial"][0]

    assert row["trial_quality"] == "clear"
    assert row["unclear_reason"] is None
    assert "short_face_dropout" in row["quality_flags"]
    assert out["counts"]["unclear"] == 0


def test_g_sub_200ms_dropout_is_bridged():
    # One 2-frame gap (~66ms) bridged by usable frames on both sides.
    frames = _frames("t1", 40, no_face=(20, 21))
    out = trial_quality.analyze("prosaccade", frames, [_Trial("t1")], CONFIG.web_capture)
    row = out["per_trial"][0]

    assert row["short_dropout"] is True
    assert row["longest_no_face_streak_ms"] <= CONFIG.web_capture.short_dropout_max_ms
    assert row["trial_quality"] == "clear"           # gaze continuity preserved
    assert row["response_detected"] is True


# ---------------------------------------------------------------------------
# B — no-face across the response window → unclear, accurate reason
# ---------------------------------------------------------------------------

def test_b_no_face_whole_response_window_is_unclear():
    frames = _frames("t1", 30, no_face=tuple(range(30)), )  # whole window no-face
    out = trial_quality.analyze(
        "prosaccade", frames, [_Trial("t1", response_detected=False)], CONFIG.web_capture
    )
    row = out["per_trial"][0]

    assert row["trial_quality"] in ("unclear", "bad")
    assert row["unclear_reason"] in (
        "no_face_at_target_onset", "insufficient_response_window_data", "no_face_major",
    )
    assert out["main_unclear_reason"] == row["unclear_reason"]


def test_b_partial_window_loss_attributes_onset():
    # Face missing for the first ~half of the window (covers target onset).
    frames = _frames("t1", 20, no_face=tuple(range(12)))
    out = trial_quality.analyze(
        "prosaccade", frames, [_Trial("t1", response_detected=False)], CONFIG.web_capture
    )
    row = out["per_trial"][0]
    assert row["no_face_near_target_onset"] is True
    assert row["trial_quality"] == "unclear"
    assert row["unclear_reason"] == "no_face_at_target_onset"


# ---------------------------------------------------------------------------
# C — high usable% but low response rate → "Okay" + trial-level suggestions
# ---------------------------------------------------------------------------

def test_c_high_usable_low_response_label_is_okay():
    # 93% usable, good confidence, but only half the rounds had a response.
    label = result_parser.quality_label(93.1, 0.805, valid_trials=6, total_trials=12)
    assert label == "Okay"


def test_c_recommendations_explain_trial_level_issue():
    trials_quality = [
        {"no_face_near_target_onset": False} for _ in range(12)
    ]
    recs = result_parser._recommendations(
        93.1, valid_trials=6, total_trials=12, blinks=2,
        well_tracked=12, trials_quality=trials_quality,
    )
    joined = " ".join(recs).lower()
    assert "unclear" in joined and "dot appear" in joined
    # Must NOT fall back to the bland "enough clear data for review" message.
    assert "enough clear data for review" not in joined


# ---------------------------------------------------------------------------
# D + E — setup / countdown frames excluded from task usable%
# ---------------------------------------------------------------------------

def test_d_setup_frames_not_counted():
    setup = _frames("", 20, no_face=tuple(range(20)), phase="waiting", rec="setup",
                    start_ms=0.0)
    task = _frames("t1", 30, phase="target", rec="task", start_ms=2000.0)
    out = trial_quality.analyze("prosaccade", setup + task, [_Trial("t1")], CONFIG.web_capture)

    fs = out["frame_stats"]
    assert fs["total_task_frames"] == 30                 # setup excluded
    assert fs["usable_eye_tracking_percent"] == 100.0    # task was clean


def test_e_countdown_frames_not_counted():
    countdown = _frames("", 15, no_face=tuple(range(15)), phase="waiting",
                        rec="countdown", start_ms=0.0)
    task = _frames("t1", 30, phase="target", rec="task", start_ms=2000.0)
    out = trial_quality.analyze("prosaccade", countdown + task, [_Trial("t1")], CONFIG.web_capture)

    fs = out["frame_stats"]
    assert fs["total_task_frames"] == 30
    assert fs["usable_eye_tracking_percent"] == 100.0


# ---------------------------------------------------------------------------
# F — no_face diagnostics by phase and by trial
# ---------------------------------------------------------------------------

def test_f_no_face_diagnostics_by_phase_and_trial():
    setup = _frames("", 10, no_face=tuple(range(10)), phase="waiting", rec="setup",
                    start_ms=0.0)
    task = _frames("t1", 30, no_face=(5, 6), phase="target", rec="task", start_ms=2000.0)
    out = trial_quality.analyze("prosaccade", setup + task, [_Trial("t1")], CONFIG.web_capture)

    nf = out["no_face"]
    assert nf["by_phase"].get("setup") == 10
    assert nf["by_phase"].get("task") == 2
    # Task-only no_face percent counts only the 2 task no-face frames of 30.
    assert nf["total_frames"] == 2
    assert nf["by_trial"][0]["trial_id"] == "t1"
    assert nf["by_trial"][0]["no_face_frames"] == 2


def test_f_main_reason_none_when_all_rounds_tracked():
    # The bug: 26/597 no-face frames must NOT make the session read "no_face".
    task = _frames("t1", 40, no_face=(10, 11), phase="target", rec="task")
    out = trial_quality.analyze("prosaccade", task, [_Trial("t1")], CONFIG.web_capture)
    assert out["main_unclear_reason"] is None
    assert out["untrackable_trials"] == 0
