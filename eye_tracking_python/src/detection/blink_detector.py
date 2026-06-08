"""
Blink detector — v0.2 fixes:
  - EAR = 0.0 (no detection) no longer triggers a blink.
    v0.1 bug: ear < 0.21 was True when ear = 0.0 (face dropout),
    causing every detection failure to count as a blink frame.
  - Adaptive baseline: the EAR threshold adapts to the user's natural
    resting EAR using a rolling maximum over the last N seconds.
    This handles users with naturally lower or higher EAR.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from config import AppConfig
from src.data.schema import BlinkEvent

logger = logging.getLogger(__name__)

# EAR must be at least this value to be considered a valid open-eye reading.
# Values at or below this are treated as "no detection", not "closed eye".
_MIN_VALID_EAR = 0.05


@dataclass
class _EyeBlinkState:
    blink_frame_count: int = 0
    is_blinking: bool = False
    blink_start_sec: float = 0.0


class BlinkDetector:
    """
    Per-session blink detector with adaptive EAR threshold.

    Usage:
        detector = BlinkDetector(config, session_id)
        event = detector.update("left",  ear_value, timestamp_sec)
        event = detector.update("right", ear_value, timestamp_sec)
    """

    def __init__(self, config: AppConfig, session_id: str = "unknown") -> None:
        self._cfg = config.blink
        self._session_id = session_id
        self._states = {
            "left": _EyeBlinkState(),
            "right": _EyeBlinkState(),
        }
        # Rolling EAR history for adaptive baseline (fps × window_sec samples)
        # We approximate fps as 30 for the buffer size.
        buf_size = max(30, int(30 * self._cfg.adaptive_baseline_window_sec))
        self._ear_history: Deque[float] = deque(maxlen=buf_size)
        self._adaptive_threshold = self._cfg.ear_closed_threshold

    def update(
        self,
        eye: str,
        ear: float,
        timestamp_sec: float,
    ) -> Optional[BlinkEvent]:
        """
        Update blink state.

        v0.2 fix: if ear <= _MIN_VALID_EAR (no detection), the frame is
        ignored entirely — it neither increments the blink counter nor resets it.
        """
        state = self._states.get(eye)
        if state is None:
            return None

        # ---- Guard: EAR = 0 means no landmark detected, not a blink --------
        if ear <= _MIN_VALID_EAR:
            return None   # skip this frame completely

        # ---- Update adaptive baseline ---------------------------------------
        self._ear_history.append(ear)
        if len(self._ear_history) >= 10:
            # Baseline = 85th percentile of recent EAR (robust open-eye estimate)
            baseline = float(
                sorted(self._ear_history)[int(0.85 * len(self._ear_history))]
            )
            # Threshold = 65% of baseline, but never below the configured minimum
            self._adaptive_threshold = max(
                self._cfg.ear_closed_threshold,
                baseline * 0.65,
            )

        # ---- Blink state machine -------------------------------------------
        eye_closed = ear < self._adaptive_threshold

        if eye_closed:
            state.blink_frame_count += 1
            if (
                not state.is_blinking
                and state.blink_frame_count >= self._cfg.ear_consec_frames
            ):
                state.is_blinking = True
                state.blink_start_sec = timestamp_sec
                logger.debug("Blink onset: eye=%s t=%.3fs", eye, timestamp_sec)
        else:
            if state.is_blinking:
                duration_ms = (timestamp_sec - state.blink_start_sec) * 1000.0
                state.is_blinking = False
                state.blink_frame_count = 0

                if (
                    self._cfg.min_blink_duration_ms
                    <= duration_ms
                    <= self._cfg.max_blink_duration_ms
                ):
                    event = BlinkEvent(
                        session_id=self._session_id,
                        start_timestamp_sec=state.blink_start_sec,
                        end_timestamp_sec=timestamp_sec,
                        duration_ms=duration_ms,
                        affected_eye=eye,
                        confidence=0.9,
                    )
                    logger.debug(
                        "Blink: eye=%s  dur=%.1fms", eye, duration_ms
                    )
                    return event
            else:
                state.blink_frame_count = 0

        return None

    def is_blinking(self, eye: str) -> bool:
        return self._states.get(eye, _EyeBlinkState()).is_blinking

    def reset(self) -> None:
        self._states = {"left": _EyeBlinkState(), "right": _EyeBlinkState()}
        self._ear_history.clear()
        self._adaptive_threshold = self._cfg.ear_closed_threshold

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id
