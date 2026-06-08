"""
Eye movement analyser.

Computes per-frame kinematics and detects three event types:

    Saccades   — fast, ballistic eye movements detected by velocity threshold
    Fixations  — stable gaze periods detected by I-DT (dispersion threshold)
    Smooth pursuit is tracked by comparing gaze to a known target trajectory
                   (target data must be passed in from the stimulus module)

All event detection algorithms are intentionally separated from the eye
tracker so they can be re-run offline on saved FrameRecord data.

Reference algorithms:
    Saccade:  velocity-threshold (Engbert & Kliegl 2003 style, simplified)
    Fixation: I-DT  (Salvucci & Goldberg 2000)
"""
from __future__ import annotations

import logging
import math
from collections import deque
from typing import Deque, List, Optional, Tuple

from config import AppConfig
from src.data.schema import FixationEvent, FrameRecord, SaccadeEvent
from src.utils.geometry import compute_angle_deg, compute_velocity, dispersion

logger = logging.getLogger(__name__)


class MovementAnalyzer:
    """
    Stateful analyser — call update() for each new FrameRecord.

    After a session, access .saccades and .fixations for event lists.
    """

    def __init__(self, config: AppConfig, session_id: str = "unknown") -> None:
        self._saccade_cfg = config.saccade
        self._fixation_cfg = config.fixation
        self._session_id = session_id

        # Rolling buffer for fixation window
        self._buffer: Deque[FrameRecord] = deque(maxlen=500)

        # Saccade state machine
        self._in_saccade = False
        self._saccade_start: Optional[FrameRecord] = None
        self._saccade_peak_velocity = 0.0

        # Fixation state
        self._fixation_candidates: List[FrameRecord] = []

        # Accumulated events for the session
        self.saccades: List[SaccadeEvent] = []
        self.fixations: List[FixationEvent] = []

    def update(self, record: FrameRecord) -> None:
        """
        Process one frame record.

        Fills in record.gaze_velocity_px_per_sec and record.gaze_acceleration
        in-place, then runs saccade and fixation detection.
        """
        self._buffer.append(record)

        if len(self._buffer) < 2:
            return

        prev = self._buffer[-2]
        curr = self._buffer[-1]

        dt = curr.timestamp_sec - prev.timestamp_sec
        if dt <= 0:
            return

        # ---- Velocity -------------------------------------------------------
        _, _, speed = compute_velocity(
            (prev.gaze_x, prev.gaze_y),
            (curr.gaze_x, curr.gaze_y),
            dt,
        )
        curr.gaze_velocity_px_per_sec = speed

        # ---- Acceleration ---------------------------------------------------
        if len(self._buffer) >= 3:
            prev_speed = prev.gaze_velocity_px_per_sec
            curr.gaze_acceleration = (speed - prev_speed) / dt

        # ---- Saccade detection ----------------------------------------------
        self._update_saccade(prev, curr, speed)

        # ---- Fixation detection (I-DT) --------------------------------------
        self._update_fixation(curr)

    def get_summary(self) -> dict:
        """Return a summary dict for export / display."""
        if not self._buffer:
            return {}

        velocities = [r.gaze_velocity_px_per_sec for r in self._buffer if r.face_detected]
        durations_fix = [e.duration_ms for e in self.fixations]
        amplitudes_sac = [e.amplitude_px for e in self.saccades]

        return {
            "saccade_count": len(self.saccades),
            "fixation_count": len(self.fixations),
            "mean_saccade_amplitude_px": float(
                sum(amplitudes_sac) / len(amplitudes_sac)
            ) if amplitudes_sac else 0.0,
            "mean_fixation_duration_ms": float(
                sum(durations_fix) / len(durations_fix)
            ) if durations_fix else 0.0,
            "mean_velocity_px_per_sec": float(
                sum(velocities) / len(velocities)
            ) if velocities else 0.0,
            "max_velocity_px_per_sec": max(velocities) if velocities else 0.0,
        }

    def reset(self, session_id: str) -> None:
        """Clear all state for a new session."""
        self._buffer.clear()
        self._in_saccade = False
        self._saccade_start = None
        self._saccade_peak_velocity = 0.0
        self._fixation_candidates = []
        self.saccades = []
        self.fixations = []
        self._session_id = session_id

    # ------------------------------------------------------------------
    # Saccade detection (velocity threshold)
    # ------------------------------------------------------------------

    def _update_saccade(
        self,
        prev: FrameRecord,
        curr: FrameRecord,
        speed: float,
    ) -> None:
        threshold = self._saccade_cfg.velocity_threshold_px_per_sec

        if not self._in_saccade:
            if speed > threshold and curr.face_detected and not curr.blink_detected:
                self._in_saccade = True
                self._saccade_start = prev
                self._saccade_peak_velocity = speed
        else:
            self._saccade_peak_velocity = max(self._saccade_peak_velocity, speed)

            if speed <= threshold or curr.blink_detected or not curr.face_detected:
                # Saccade ended
                if self._saccade_start is not None:
                    self._emit_saccade(self._saccade_start, curr)
                self._in_saccade = False
                self._saccade_start = None
                self._saccade_peak_velocity = 0.0

    def _emit_saccade(self, start: FrameRecord, end: FrameRecord) -> None:
        duration_ms = (end.timestamp_sec - start.timestamp_sec) * 1000.0

        if not (
            self._saccade_cfg.min_duration_ms
            <= duration_ms
            <= self._saccade_cfg.max_duration_ms
        ):
            return

        dx = end.gaze_x - start.gaze_x
        dy = end.gaze_y - start.gaze_y
        amplitude = math.hypot(dx, dy)

        if amplitude < self._saccade_cfg.min_amplitude_px:
            return

        direction = compute_angle_deg(dx, dy)

        event = SaccadeEvent(
            session_id=self._session_id,
            start_timestamp_sec=start.timestamp_sec,
            end_timestamp_sec=end.timestamp_sec,
            duration_ms=duration_ms,
            start_x=start.gaze_x,
            start_y=start.gaze_y,
            end_x=end.gaze_x,
            end_y=end.gaze_y,
            amplitude_px=amplitude,
            peak_velocity_px_per_sec=self._saccade_peak_velocity,
            direction_deg=direction,
        )
        self.saccades.append(event)
        logger.debug(
            "Saccade: amp=%.1f px  dur=%.1f ms  peak=%.0f px/s",
            amplitude, duration_ms, self._saccade_peak_velocity,
        )

    # ------------------------------------------------------------------
    # Fixation detection (I-DT algorithm)
    # ------------------------------------------------------------------

    def _update_fixation(self, record: FrameRecord) -> None:
        """
        Incremental I-DT: accumulate frames into a candidate window.
        When dispersion exceeds the threshold, check if we have a valid
        fixation then start fresh.
        """
        if not record.face_detected or record.blink_detected:
            # Flush any pending fixation candidate
            if len(self._fixation_candidates) >= self._fixation_cfg.window_size_frames:
                self._maybe_emit_fixation()
            self._fixation_candidates = []
            return

        self._fixation_candidates.append(record)

        pts: List[Tuple[float, float]] = [
            (r.gaze_x, r.gaze_y) for r in self._fixation_candidates
        ]
        disp = dispersion(pts)

        if disp > self._fixation_cfg.max_dispersion_px:
            # Dispersion exceeded — emit fixation from all but last record
            window = self._fixation_candidates[:-1]
            if len(window) >= self._fixation_cfg.window_size_frames:
                self._emit_fixation(window)
            # Start a new window from the current (potentially new fixation start)
            self._fixation_candidates = [record]

    def _maybe_emit_fixation(self) -> None:
        if len(self._fixation_candidates) >= self._fixation_cfg.window_size_frames:
            self._emit_fixation(self._fixation_candidates)
        self._fixation_candidates = []

    def _emit_fixation(self, window: List[FrameRecord]) -> None:
        if not window:
            return

        duration_ms = (window[-1].timestamp_sec - window[0].timestamp_sec) * 1000.0
        if duration_ms < self._fixation_cfg.min_duration_ms:
            return

        xs = [r.gaze_x for r in window]
        ys = [r.gaze_y for r in window]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        pts = list(zip(xs, ys))
        disp = dispersion(pts)

        event = FixationEvent(
            session_id=self._session_id,
            start_timestamp_sec=window[0].timestamp_sec,
            end_timestamp_sec=window[-1].timestamp_sec,
            duration_ms=duration_ms,
            center_x=cx,
            center_y=cy,
            dispersion_px=disp,
        )
        self.fixations.append(event)
        logger.debug(
            "Fixation: duration=%.1f ms  centre=(%.2f, %.2f)  disp=%.1f px",
            duration_ms, cx, cy, disp,
        )
