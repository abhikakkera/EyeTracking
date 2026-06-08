"""
Threaded camera wrapper.

Wraps any CameraInterface and reads frames in a background thread.
The processing thread always gets the latest frame instead of blocking
on camera I/O — this alone can double effective tracking FPS.

A queue of size 1 is used so the processing thread always gets the
most recent frame (old frames are dropped, not buffered).
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional, Tuple

from src.camera.camera_interface import CameraInterface
from src.data.schema import FrameData

logger = logging.getLogger(__name__)


class ThreadedCameraStream(CameraInterface):
    """
    Drop-in replacement for any CameraInterface that reads in a background thread.

    Usage:
        base = WebcamStream(0)
        camera = ThreadedCameraStream(base)
        camera.start()           # starts background capture thread
        frame = camera.read_frame()
        camera.stop()
    """

    def __init__(self, camera: CameraInterface) -> None:
        self._camera = camera
        # Queue size 1 — always keep only the newest frame
        self._queue: queue.Queue[Optional[FrameData]] = queue.Queue(maxsize=1)
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # CameraInterface
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._camera.start()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="CameraCapture",
            daemon=True,
        )
        self._thread.start()
        logger.info("Threaded camera capture started.")

    def read_frame(self) -> Optional[FrameData]:
        """
        Return the latest available frame.
        Blocks up to 100 ms; returns None if no frame arrives (source ended).
        """
        try:
            return self._queue.get(timeout=0.1)
        except queue.Empty:
            return None if not self._running else None

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._camera.stop()
        logger.info("Threaded camera stopped.")

    def get_fps(self) -> float:
        return self._camera.get_fps()

    def get_resolution(self) -> Tuple[int, int]:
        return self._camera.get_resolution()

    @property
    def is_open(self) -> bool:
        return self._running and self._camera.is_open

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Continuously read from the underlying camera and post to the queue."""
        while self._running:
            frame = self._camera.read_frame()
            if frame is None:
                logger.debug("Camera source exhausted — stopping capture thread.")
                self._running = False
                break

            # Drop stale frame if consumer is slow (keep only latest)
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put(frame)
