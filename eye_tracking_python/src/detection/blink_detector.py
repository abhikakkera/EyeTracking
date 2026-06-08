"""
Blink detector using the Eye Aspect Ratio (EAR).

EAR = (‖P2-P6‖ + ‖P3-P5‖) / (2 · ‖P1-P4‖)
(Soukupova & Cech, "Real-Time Eye Blink Detection using Facial Landmarks",
 CVWW 2016)

A blink is detected when EAR drops below the configured threshold for at
least `ear_consec_frames` consecutive frames and then rises again.

The detector maintains independent state machines for left and right eyes.
The BlinkEvent is emitted when the eye re-opens (i.e. on the rising edge).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import AppConfig
from src.data.schema import BlinkEvent

logger = logging.getLogger(__name__)


@dataclass
class _EyeBlinkState:
    """Internal per-eye state for the blink state machine."""
    blink_frame_count: int = 0
    is_blinking: bool = False
    blink_start_sec: float = 0.0


class BlinkDetector:
    """
    Per-session blink detector.  Call update() once per frame per eye.

    Usage:
        detector = BlinkDetector(config, session_id)
        event = detector.update("left",  ear_value, timestamp_sec)
        event = detector.update("right", ear_value, timestamp_sec)
        # event is None most frames; a BlinkEvent when a blink completes.
    """

    def __init__(self, config: AppConfig, session_id: str = "unknown") -> None:
        self._cfg = config.blink
        self._session_id = session_id
        self._states = {
            "left": _EyeBlinkState(),
            "right": _EyeBlinkState(),
        }

    def update(
        self,
        eye: str,
        ear: float,
        timestamp_sec: float,
    ) -> Optional[BlinkEvent]:
        """
        Update blink state for one eye.

        Parameters
        ----------
        eye : "left" or "right"
        ear : current Eye Aspect Ratio value
        timestamp_sec : current frame timestamp in seconds

        Returns
        -------
        BlinkEvent if a blink just completed (eye re-opened), else None.
        """
        state = self._states.get(eye)
        if state is None:
            return None

        eye_closed = ear < self._cfg.ear_closed_threshold

        if eye_closed:
            state.blink_frame_count += 1
            if not state.is_blinking and state.blink_frame_count >= self._cfg.ear_consec_frames:
                # Blink onset confirmed
                state.is_blinking = True
                state.blink_start_sec = timestamp_sec
                logger.debug("Blink onset: eye=%s t=%.3f", eye, timestamp_sec)
        else:
            if state.is_blinking:
                # Blink offset — eye re-opened
                duration_ms = (timestamp_sec - state.blink_start_sec) * 1000.0

                # Validate duration
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
                        "Blink complete: eye=%s  duration=%.1f ms", eye, duration_ms
                    )
                    state.is_blinking = False
                    state.blink_frame_count = 0
                    return event
                else:
                    logger.debug(
                        "Blink rejected: eye=%s  duration=%.1f ms (out of range)",
                        eye, duration_ms,
                    )

            state.is_blinking = False
            state.blink_frame_count = 0

        return None

    def is_blinking(self, eye: str) -> bool:
        """Return True if the specified eye is currently in a blink."""
        return self._states.get(eye, _EyeBlinkState()).is_blinking

    def reset(self) -> None:
        """Reset state for both eyes (e.g. at session start)."""
        self._states = {
            "left": _EyeBlinkState(),
            "right": _EyeBlinkState(),
        }

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id
