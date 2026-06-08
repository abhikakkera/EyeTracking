"""
Session recorder.

Accumulates FrameRecord, BlinkEvent, SaccadeEvent, and FixationEvent objects
during a tracking session and exposes them for export.

The recorder is intentionally stateless between sessions — call start() to
begin and finish() to close, then access .current_session for the data.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from src.data.schema import (
    BlinkEvent, FixationEvent, FrameRecord,
    FrameQuality, SaccadeEvent, SessionMetadata,
)
from src.utils.timing import current_timestamp

logger = logging.getLogger(__name__)


class SessionData:
    """Container for all data collected during one session."""

    def __init__(self, metadata: SessionMetadata) -> None:
        self.metadata = metadata
        self.frames: List[FrameRecord] = []
        self.blinks: List[BlinkEvent] = []
        self.saccades: List[SaccadeEvent] = []
        self.fixations: List[FixationEvent] = []


class SessionRecorder:
    """
    Accumulates tracking data for one session.

    Usage:
        recorder = SessionRecorder()
        recorder.start(metadata)
        recorder.add_frame(record)        # called per frame
        recorder.add_blink(blink_event)   # called when blink detector fires
        session = recorder.finish(saccades, fixations)
    """

    def __init__(self) -> None:
        self._session: Optional[SessionData] = None

    def start(self, metadata: SessionMetadata) -> None:
        self._session = SessionData(metadata)
        logger.info("Recording started: session_id=%s", metadata.session_id)

    def add_frame(self, record: FrameRecord) -> None:
        if self._session is None:
            logger.warning("add_frame called before start()")
            return
        self._session.frames.append(record)

    def add_blink(self, event: BlinkEvent) -> None:
        if self._session is None:
            return
        self._session.blinks.append(event)

    def finish(
        self,
        saccades: Optional[List[SaccadeEvent]] = None,
        fixations: Optional[List[FixationEvent]] = None,
    ) -> SessionMetadata:
        """
        Finalise the session.  Fills in summary counts and timestamps.
        Returns the completed SessionMetadata.
        """
        if self._session is None:
            raise RuntimeError("finish() called without a preceding start()")

        meta = self._session.metadata
        meta.timestamp_end = current_timestamp()

        frames = self._session.frames
        meta.total_frames = len(frames)
        meta.good_frames = sum(
            1 for f in frames if f.frame_quality == FrameQuality.GOOD
        )
        meta.blink_count = len(self._session.blinks)

        if saccades:
            self._session.saccades = saccades
        if fixations:
            self._session.fixations = fixations

        meta.saccade_count = len(self._session.saccades)
        meta.fixation_count = len(self._session.fixations)

        if frames:
            meta.fps = len(frames) / max(
                frames[-1].timestamp_sec - frames[0].timestamp_sec, 1e-9
            )

        logger.info(
            "Session finished: frames=%d  good=%d  blinks=%d  saccades=%d  fixations=%d",
            meta.total_frames, meta.good_frames,
            meta.blink_count, meta.saccade_count, meta.fixation_count,
        )
        return meta

    @property
    def current_session(self) -> Optional[SessionData]:
        return self._session

    @property
    def frame_count(self) -> int:
        if self._session is None:
            return 0
        return len(self._session.frames)
