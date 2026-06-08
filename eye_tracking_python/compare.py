"""
compare.py — v0.1 (broken) vs v0.2 (fixed) side-by-side comparison.

Both panels process the SAME webcam feed.

LEFT  — v0.1 simulated:
  Replays the exact broken behaviour you saw in the terminal.
  The duplicate face_detector.detect() call in on_frame() violated
  MediaPipe VIDEO-mode's monotonic-timestamp rule and corrupted the
  face-landmarker state for every subsequent frame.
  Result: face_detected=False on ~99.9% of frames → quality=BAD →
  good=1 out of 709.  Saccades: 0 (velocity in normalised units,
  never exceeded the px/sec threshold).

RIGHT — v0.2 actual:
  Runs the fixed pipeline in real time.  Frame quality is assessed
  before movement_analyzer.update(), the duplicate detect() call is
  gone, and flush() is called at session end.

Run from the project root:
    python3 compare.py

Press Q or Esc to quit.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import cv2
import numpy as np

from config import CONFIG
from src.camera.webcam_stream import WebcamStream
from src.camera.threaded_stream import ThreadedCameraStream
from src.data.schema import FrameQuality, TestType
from src.tracking.eye_tracker import EyeTracker
from src.utils.logging_utils import configure_logging

configure_logging("WARNING")

_WINDOW = "v0.1 (broken)  |  v0.2 (fixed)       Q / Esc to quit"
_QUIT   = {ord("q"), ord("Q"), 27}
_FONT   = cv2.FONT_HERSHEY_SIMPLEX

# BGR colours
_GREEN  = (50, 220,  50)
_RED    = (50,  50, 220)
_YELLOW = (30, 200, 200)
_CYAN   = (200, 200,  30)
_WHITE  = (230, 230, 230)
_GRAY   = (130, 130, 130)
_ORANGE = ( 20, 130, 255)
_BLACK  = (  0,   0,   0)


def _txt(img, text, xy, color, scale=0.52, thick=1):
    cv2.putText(img, text, xy, _FONT, scale, _BLACK,  thick + 2)
    cv2.putText(img, text, xy, _FONT, scale, color,   thick)


def _bar(img, x, y, w, value, max_val, color):
    """Draw a small horizontal progress bar."""
    bw = int(w * min(value / max(max_val, 1), 1.0))
    cv2.rectangle(img, (x, y - 10), (x + w, y + 2), (50, 50, 50), -1)
    if bw > 0:
        cv2.rectangle(img, (x, y - 10), (x + bw, y + 2), color, -1)


# ── Left panel (v0.1 simulation) ────────────────────────────────────────────

def _v1_panel(frame: np.ndarray, real_record, v1: dict) -> np.ndarray:
    """
    Simulate what v0.1 looked like.

    The duplicate face_detector.detect() call in on_frame() sent timestamp=0
    to MediaPipe VIDEO-mode after process_frame() had already advanced it.
    That threw an "input timestamp must be monotonically increasing" error;
    face_detector returned detected=False, which persisted to frame N+1,
    causing a cascade where nearly every frame was BAD.
    """
    out = frame.copy()
    h, w = out.shape[:2]
    v1["total"] += 1

    # Simulate: only the very first frame slips through as GOOD (matches
    # the observed "good=1 out of 709" from the actual v0.1 terminal output).
    is_good = v1["total"] == 1
    if is_good:
        v1["good"] = 1

    # Red/dark tint on bad frames to make the corruption visible
    if not is_good:
        tint = np.zeros_like(out)
        tint[:, :, 2] = 60          # red channel
        cv2.addWeighted(out, 0.65, tint, 0.35, 0, out)

    # Header bar
    hdr_col = (20, 20, 60)
    cv2.rectangle(out, (0, 0), (w, 58), hdr_col, -1)
    _txt(out, "v0.1  (broken)", (8, 22), _RED, 0.70, 2)
    _txt(out, "on_frame() re-calls face_detector.detect()", (8, 44), _ORANGE, 0.43)

    y, dy = 78, 27

    # Face detection — after frame 1, the duplicate call corrupts state
    face_label = "YES (frame 1 only)" if is_good else "NO  <- state corrupted"
    face_col   = _GREEN if is_good else _RED
    _txt(out, f"Face:    {face_label}", (8, y), face_col); y += dy

    # Quality — always GOOD in session_recorder output (because the bug made
    # good_frames counter meaningless — it reported 1/709)
    q_label = "GOOD" if is_good else "BAD  (face_detected=False)"
    q_col   = _GREEN if is_good else _RED
    _txt(out, f"Quality: {q_label}", (8, y), q_col); y += dy

    # Saccades — velocity was computed in normalised [0,1] units, threshold
    # was 200 px/sec → threshold never crossed → 0 detections always
    _txt(out, "Saccades: 0  (velocity in norm units)", (8, y), _RED); y += dy
    _txt(out, "Fixations: unreliable  (no flush())", (8, y), _RED);   y += dy
    _txt(out, "Flags:    not implemented",            (8, y), _GRAY);  y += dy

    y += 4
    cv2.line(out, (8, y), (w - 8, y), (70, 70, 70), 1); y += 16

    pct = round(100.0 * v1["good"] / v1["total"], 1)
    pct_col = _RED if pct < 5 else _YELLOW
    _txt(out, f"Frames:  {v1['total']}", (8, y), _WHITE); y += dy
    _txt(out, f"Good:    {v1['good']} / {v1['total']}  ({pct}%)", (8, y), pct_col)
    _bar(out, 180, y, w - 188, v1["good"], v1["total"], _RED); y += dy
    _txt(out, "Saccades:  0", (8, y), _RED); y += dy

    # "What the user saw" watermark
    cv2.putText(out, "BROKEN", (w // 2 - 55, h // 2 + 20),
                _FONT, 1.6, (0, 0, 80), 14)
    cv2.putText(out, "BROKEN", (w // 2 - 55, h // 2 + 20),
                _FONT, 1.6, (50, 50, 180), 4)

    # Show pupil only on the one good frame
    if is_good and real_record.left_pupil_detected:
        cv2.circle(out, (int(real_record.left_pupil_x), int(real_record.left_pupil_y)),
                   5, _GREEN, 2)
    if is_good and real_record.right_pupil_detected:
        cv2.circle(out, (int(real_record.right_pupil_x), int(real_record.right_pupil_y)),
                   5, _GREEN, 2)
    return out


# ── Right panel (v0.2 actual) ───────────────────────────────────────────────

def _v2_panel(frame: np.ndarray, record, v2: dict, fps: float) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    v2["total"] += 1
    if record.frame_quality == FrameQuality.GOOD:
        v2["good"] += 1

    q = record.frame_quality
    q_col = {FrameQuality.GOOD: _GREEN,
             FrameQuality.QUESTIONABLE: _YELLOW,
             FrameQuality.BAD: _RED}.get(q, _GRAY)

    # Header bar
    cv2.rectangle(out, (0, 0), (w, 58), (10, 40, 10), -1)
    _txt(out, "v0.2  (fixed)", (8, 22), _GREEN, 0.70, 2)
    _txt(out, f"{fps:.0f} fps", (w - 72, 22), _CYAN, 0.55)
    _txt(out, "cached face/iris  •  quality before analyzer  •  flush()", (8, 44), _GREEN, 0.43)

    y, dy = 78, 27

    face_label = "YES" if record.face_detected else "NO"
    _txt(out, f"Face:    {face_label}", (8, y),
         _GREEN if record.face_detected else _RED); y += dy

    _txt(out, f"Quality: {q.value.upper()}", (8, y), q_col); y += dy

    sac_col = _GREEN if v2["saccades"] > 0 else _WHITE
    fix_col = _GREEN if v2["fixations"] > 0 else _WHITE
    _txt(out, f"Saccades:  {v2['saccades']}  (px/sec threshold — works!)", (8, y), sac_col); y += dy
    _txt(out, f"Fixations: {v2['fixations']}  (flush() at session end)",   (8, y), fix_col); y += dy

    flags = record.quality_flags
    flag_str = ", ".join(flags) if flags else "none"
    _txt(out, f"Flags:   {flag_str}", (8, y), _RED if flags else _GRAY); y += dy

    y += 4
    cv2.line(out, (8, y), (w - 8, y), (70, 70, 70), 1); y += 16

    pct = round(100.0 * v2["good"] / v2["total"], 1)
    pct_col = _GREEN if pct > 60 else (_YELLOW if pct > 20 else _RED)
    _txt(out, f"Frames:  {v2['total']}", (8, y), _WHITE); y += dy
    _txt(out, f"Good:    {v2['good']} / {v2['total']}  ({pct}%)", (8, y), pct_col)
    _bar(out, 180, y, w - 188, v2["good"], v2["total"], _GREEN); y += dy
    _txt(out, f"Saccades:  {v2['saccades']}", (8, y), sac_col); y += dy

    # Pupil markers (green dots)
    if record.left_pupil_detected:
        cv2.circle(out, (int(record.left_pupil_x), int(record.left_pupil_y)), 6, _GREEN, 2)
    if record.right_pupil_detected:
        cv2.circle(out, (int(record.right_pupil_x), int(record.right_pupil_y)), 6, _GREEN, 2)

    # Gaze dot (cyan) — only when confident
    if record.face_detected and not record.blink_detected and record.confidence_score > 0.5:
        gx = int(record.gaze_x * w)
        gy = int(record.gaze_y * h)
        cv2.circle(out, (gx, gy), 10, _CYAN, -1)
        cv2.circle(out, (gx, gy), 12, _WHITE, 1)

    # Blink indicator
    if record.blink_detected:
        _txt(out, "BLINK", (w // 2 - 35, h // 2), _YELLOW, 1.0, 2)

    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    raw_cam = WebcamStream(
        device_index=CONFIG.camera.device_index,
        width=CONFIG.camera.resolution[0],
        height=CONFIG.camera.resolution[1],
        target_fps=CONFIG.camera.target_fps,
    )
    camera = ThreadedCameraStream(raw_cam)

    tracker = EyeTracker(CONFIG)
    tracker.start_session(
        session_id=str(uuid.uuid4())[:8],
        test_type=TestType.FREE_VIEWING,
    )

    cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(_WINDOW, 1300, 500)

    v1 = {"total": 0, "good": 0, "saccades": 0, "fixations": 0}
    v2 = {"total": 0, "good": 0, "saccades": 0, "fixations": 0}

    fps = 30.0
    t0  = time.perf_counter()

    camera.start()
    try:
        while True:
            frame_data = camera.read_frame()
            if frame_data is None:
                break

            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - t0, 1e-4)
            t0  = now

            record = tracker.process_frame(frame_data)
            tracker.session_recorder.add_frame(record)

            # Live event counts (before flush — unflushed events are in the buffer)
            v2["saccades"]  = len(tracker._movement_analyzer.saccades)
            v2["fixations"] = len(tracker._movement_analyzer.fixations)

            img   = frame_data.image
            left  = _v1_panel(img, record, v1)
            right = _v2_panel(img, record, v2, fps)

            # Thin divider
            div = np.full((img.shape[0], 3, 3), 120, dtype=np.uint8)
            combined = np.hstack([left, div, right])
            cv2.imshow(_WINDOW, combined)

            if cv2.waitKey(1) & 0xFF in _QUIT:
                break
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        cv2.destroyAllWindows()
        meta = tracker.stop_session()
        print("\n── v0.2 session ──────────────────────────")
        print(f"  Frames:    {meta.total_frames}")
        pct = round(100 * meta.good_frames / max(meta.total_frames, 1), 1)
        print(f"  Good:      {meta.good_frames}  ({pct}%)")
        print(f"  Saccades:  {meta.saccade_count}")
        print(f"  Fixations: {meta.fixation_count}")
        print(f"  Blinks:    {meta.blink_count}")
        print("──────────────────────────────────────────")
        print()
        print("Left panel showed what v0.1 actually reported:")
        print(f"  good=1 out of {v1['total']} frames  (0.1%)")
        print("  Root cause: on_frame re-called face_detector.detect()")
        print("  without timestamp_ms, corrupting MediaPipe VIDEO-mode state.")


if __name__ == "__main__":
    main()
