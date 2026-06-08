"""
Eye movement analyser — v0.2 fixes.

Bug fixes from v0.1:
  1. Velocity now computed on ACTUAL PUPIL PIXEL COORDINATES (left_pupil_x/y,
     right_pupil_x/y), not on normalised gaze (gaze_x/y ∈ [0,1]).
     In v0.1, velocity was always < 1.0 normalised/sec while the threshold
     was 500 px/sec → saccades were never detected.

  2. fixation_candidates is now bounded.
     v0.1 used a plain List that grew unbounded during long fixations
     (e.g. user stares at screen for 2 minutes → 3600 frames in memory).
     v0.2 caps it at config.fixation.max_candidate_frames and periodically
     emits fixation events for very long stable gaze periods.

  3. Jerk (3rd derivative of position) is computed and stored.

  4. Quality-filtered metrics in get_summary() exclude bad/blink frames.

  5. SaccadeEvent and FixationEvent now carry event_id, mean_velocity, num_frames.
"""
from __future__ import annotations

import logging
import math
import uuid
from collections import deque
from typing import Deque, List, Optional, Tuple

from config import AppConfig
from src.data.schema import FixationEvent, FrameRecord, SaccadeEvent
from src.utils.geometry import compute_angle_deg, compute_velocity, dispersion

logger = logging.getLogger(__name__)


class MovementAnalyzer:
    """
    Stateful analyser — call update() once per FrameRecord.

    Access .saccades and .fixations after a session for all detected events.
    """

    def __init__(self, config: AppConfig, session_id: str = "unknown") -> None:
        self._saccade_cfg = config.saccade
        self._fixation_cfg = config.fixation
        self._session_id = session_id

        # Rolling buffer for velocity/acceleration computation
        self._buffer: Deque[FrameRecord] = deque(maxlen=500)

        # Saccade state machine
        self._in_saccade = False
        self._saccade_start: Optional[FrameRecord] = None
        self._saccade_peak_velocity = 0.0
        self._saccade_velocity_sum = 0.0
        self._saccade_frame_count = 0

        # Fixation state — BOUNDED list (v0.1 bug fix)
        self._fixation_candidates: List[FrameRecord] = []

        self.saccades: List[SaccadeEvent] = []
        self.fixations: List[FixationEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, record: FrameRecord) -> None:
        """
        Process one frame. Updates record kinematics in-place then runs
        saccade and fixation detection.
        """
        self._buffer.append(record)

        if len(self._buffer) < 2:
            return

        prev = self._buffer[-2]
        curr = self._buffer[-1]

        dt = curr.timestamp_sec - prev.timestamp_sec
        if dt <= 1e-6:
            return

        # ---- Velocity in PIXEL SPACE (Bug 1 fix) ----------------------------
        curr_pos = self._best_pixel_pos(curr)
        prev_pos = self._best_pixel_pos(prev)

        if curr_pos is not None and prev_pos is not None:
            _, _, speed = compute_velocity(prev_pos, curr_pos, dt)
            curr.gaze_velocity_px_per_sec = speed
        else:
            curr.gaze_velocity_px_per_sec = 0.0

        # ---- Acceleration ---------------------------------------------------
        if len(self._buffer) >= 3:
            prev_speed = prev.gaze_velocity_px_per_sec
            curr.gaze_acceleration_px_per_sec2 = (
                (curr.gaze_velocity_px_per_sec - prev_speed) / dt
            )

        # ---- Jerk (3rd derivative) ------------------------------------------
        if len(self._buffer) >= 4:
            prev2 = self._buffer[-3]
            curr.gaze_jerk_px_per_sec3 = (
                (curr.gaze_acceleration_px_per_sec2 - prev.gaze_acceleration_px_per_sec2) / dt
            )

        # ---- Saccade detection ----------------------------------------------
        if curr_pos is not None and prev_pos is not None:
            self._update_saccade(prev, curr, curr.gaze_velocity_px_per_sec)

        # ---- Fixation detection (I-DT) with bounded list -------------------
        self._update_fixation(curr)

    def flush(self) -> None:
        """
        Flush any pending fixation at the end of a session.
        Call this before accessing .fixations.
        """
        if self._fixation_candidates:
            self._emit_fixation(self._fixation_candidates)
            self._fixation_candidates = []

        # Close any open saccade
        if self._in_saccade and self._saccade_start is not None and self._buffer:
            self._emit_saccade(self._saccade_start, self._buffer[-1])
            self._in_saccade = False
            self._saccade_start = None

    def get_summary(self) -> dict:
        """
        Summary statistics, excluding blink frames and bad-quality frames.
        """
        good_frames = [
            r for r in self._buffer
            if r.face_detected
            and not r.blink_detected
            and r.frame_quality.value != "bad"
        ]
        velocities = [r.gaze_velocity_px_per_sec for r in good_frames]
        sac_amps = [e.amplitude_px for e in self.saccades]
        sac_vels = [e.peak_velocity_px_per_sec for e in self.saccades]
        sac_means = [e.mean_velocity_px_per_sec for e in self.saccades]
        fix_durs = [e.duration_ms for e in self.fixations]
        bad_count = sum(1 for r in self._buffer if r.frame_quality.value == "bad")

        return {
            "saccade_count": len(self.saccades),
            "fixation_count": len(self.fixations),
            "mean_saccade_amplitude_px": _safe_mean(sac_amps),
            "mean_saccade_peak_velocity_px_per_sec": _safe_mean(sac_vels),
            "mean_saccade_mean_velocity_px_per_sec": _safe_mean(sac_means),
            "mean_fixation_duration_ms": _safe_mean(fix_durs),
            "max_fixation_duration_ms": max(fix_durs) if fix_durs else 0.0,
            "mean_gaze_velocity_px_per_sec": _safe_mean(velocities),
            "max_gaze_velocity_px_per_sec": max(velocities) if velocities else 0.0,
            "bad_frame_count": bad_count,
            "bad_frame_pct": round(100.0 * bad_count / max(len(self._buffer), 1), 1),
        }

    def reset(self, session_id: str) -> None:
        self._buffer.clear()
        self._in_saccade = False
        self._saccade_start = None
        self._saccade_peak_velocity = 0.0
        self._saccade_velocity_sum = 0.0
        self._saccade_frame_count = 0
        self._fixation_candidates = []
        self.saccades = []
        self.fixations = []
        self._session_id = session_id

    # ------------------------------------------------------------------
    # Pixel-space position helper (Bug 1 fix)
    # ------------------------------------------------------------------

    @staticmethod
    def _best_pixel_pos(record: FrameRecord) -> Optional[Tuple[float, float]]:
        """
        Return the best available pupil position in actual frame PIXEL coords.
        Prefer the average of both pupils; fall back to whichever is detected.
        Used for velocity computation (NOT normalised gaze).
        """
        if not record.face_detected:
            return None
        if record.blink_detected:
            return None

        left_ok = record.left_pupil_detected
        right_ok = record.right_pupil_detected

        if left_ok and right_ok:
            return (
                (record.left_pupil_x + record.right_pupil_x) / 2.0,
                (record.left_pupil_y + record.right_pupil_y) / 2.0,
            )
        if left_ok:
            return (record.left_pupil_x, record.left_pupil_y)
        if right_ok:
            return (record.right_pupil_x, record.right_pupil_y)
        return None

    # ------------------------------------------------------------------
    # Saccade detection
    # ------------------------------------------------------------------

    def _update_saccade(
        self,
        prev: FrameRecord,
        curr: FrameRecord,
        speed: float,
    ) -> None:
        threshold = self._saccade_cfg.velocity_threshold_px_per_sec

        if not self._in_saccade:
            if (
                speed > threshold
                and curr.face_detected
                and not curr.blink_detected
                and curr.frame_quality.value != "bad"
            ):
                self._in_saccade = True
                self._saccade_start = prev
                self._saccade_peak_velocity = speed
                self._saccade_velocity_sum = speed
                self._saccade_frame_count = 1
        else:
            self._saccade_peak_velocity = max(self._saccade_peak_velocity, speed)
            self._saccade_velocity_sum += speed
            self._saccade_frame_count += 1

            if speed <= threshold or curr.blink_detected or not curr.face_detected:
                if self._saccade_start is not None:
                    self._emit_saccade(self._saccade_start, curr)
                self._in_saccade = False
                self._saccade_start = None
                self._saccade_peak_velocity = 0.0
                self._saccade_velocity_sum = 0.0
                self._saccade_frame_count = 0

    def _emit_saccade(self, start: FrameRecord, end: FrameRecord) -> None:
        duration_ms = (end.timestamp_sec - start.timestamp_sec) * 1000.0
        if not (
            self._saccade_cfg.min_duration_ms
            <= duration_ms
            <= self._saccade_cfg.max_duration_ms
        ):
            return

        # Amplitude uses the actual pixel positions
        start_pos = self._best_pixel_pos(start)
        end_pos = self._best_pixel_pos(end)
        if start_pos is None or end_pos is None:
            return

        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        amplitude = math.hypot(dx, dy)

        if amplitude < self._saccade_cfg.min_amplitude_px:
            return

        mean_vel = (
            self._saccade_velocity_sum / self._saccade_frame_count
            if self._saccade_frame_count > 0
            else self._saccade_peak_velocity
        )

        event = SaccadeEvent(
            session_id=self._session_id,
            start_timestamp_sec=start.timestamp_sec,
            end_timestamp_sec=end.timestamp_sec,
            duration_ms=duration_ms,
            start_x=start_pos[0],
            start_y=start_pos[1],
            end_x=end_pos[0],
            end_y=end_pos[1],
            amplitude_px=amplitude,
            peak_velocity_px_per_sec=self._saccade_peak_velocity,
            mean_velocity_px_per_sec=mean_vel,
            direction_deg=compute_angle_deg(dx, dy),
        )
        self.saccades.append(event)
        logger.debug(
            "Saccade: amp=%.1fpx  dur=%.1fms  peak=%.0fpx/s",
            amplitude, duration_ms, self._saccade_peak_velocity,
        )

    # ------------------------------------------------------------------
    # Fixation detection (I-DT) — bounded list fix
    # ------------------------------------------------------------------

    def _update_fixation(self, record: FrameRecord) -> None:
        """
        Incremental I-DT with bounded candidate list.
        The list is capped at max_candidate_frames; when it reaches the cap
        we emit the current fixation and start fresh (handles very long fixations).
        """
        if (
            not record.face_detected
            or record.blink_detected
            or record.frame_quality.value == "bad"
        ):
            if len(self._fixation_candidates) >= self._fixation_cfg.window_size_frames:
                self._emit_fixation(self._fixation_candidates)
            self._fixation_candidates = []
            return

        self._fixation_candidates.append(record)

        # --- Cap the list (Bug 2 fix) ----------------------------------------
        if len(self._fixation_candidates) >= self._fixation_cfg.max_candidate_frames:
            self._emit_fixation(self._fixation_candidates)
            self._fixation_candidates = []
            return

        pts: List[Tuple[float, float]] = [
            (r.left_pupil_x if r.left_pupil_detected else r.gaze_x,
             r.left_pupil_y if r.left_pupil_detected else r.gaze_y)
            for r in self._fixation_candidates
        ]
        disp = dispersion(pts)

        if disp > self._fixation_cfg.max_dispersion_px:
            window = self._fixation_candidates[:-1]
            if len(window) >= self._fixation_cfg.window_size_frames:
                self._emit_fixation(window)
            self._fixation_candidates = [record]

    def _emit_fixation(self, window: List[FrameRecord]) -> None:
        if not window:
            return
        duration_ms = (window[-1].timestamp_sec - window[0].timestamp_sec) * 1000.0
        if duration_ms < self._fixation_cfg.min_duration_ms:
            return

        xs = [r.left_pupil_x if r.left_pupil_detected else r.gaze_x for r in window]
        ys = [r.left_pupil_y if r.left_pupil_detected else r.gaze_y for r in window]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        disp = dispersion(list(zip(xs, ys)))

        event = FixationEvent(
            session_id=self._session_id,
            start_timestamp_sec=window[0].timestamp_sec,
            end_timestamp_sec=window[-1].timestamp_sec,
            duration_ms=duration_ms,
            center_x=cx,
            center_y=cy,
            dispersion_px=disp,
            num_frames=len(window),
        )
        self.fixations.append(event)
        logger.debug(
            "Fixation: dur=%.1fms  centre=(%.1f, %.1f)  disp=%.1fpx  frames=%d",
            duration_ms, cx, cy, disp, len(window),
        )


def _safe_mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0
