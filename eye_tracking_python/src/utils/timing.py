"""
High-resolution timing utilities.
Eye movement analysis depends on accurate per-frame timestamps.
time.perf_counter() is used rather than time.time() for sub-millisecond precision.
"""
from __future__ import annotations

import time


class PrecisionTimer:
    """Wall-clock timer backed by time.perf_counter."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self._running: bool = False

    def start(self) -> None:
        self._start = time.perf_counter()
        self._running = True

    def elapsed_seconds(self) -> float:
        if not self._running:
            return 0.0
        return time.perf_counter() - self._start

    def elapsed_ms(self) -> float:
        return self.elapsed_seconds() * 1000.0

    def reset(self) -> None:
        """Restart the timer without stopping it."""
        self._start = time.perf_counter()


class FPSCounter:
    """Rolling-window FPS estimator."""

    def __init__(self, window: int = 30) -> None:
        self._window = window
        self._timestamps: list[float] = []

    def tick(self) -> None:
        """Record a new frame arrival."""
        self._timestamps.append(time.perf_counter())
        if len(self._timestamps) > self._window:
            self._timestamps.pop(0)

    @property
    def fps(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        span = self._timestamps[-1] - self._timestamps[0]
        if span <= 0:
            return 0.0
        return (len(self._timestamps) - 1) / span

    def reset(self) -> None:
        self._timestamps.clear()


def current_timestamp() -> float:
    """Return the current Unix epoch time as a float."""
    return time.time()


def frame_index_to_seconds(frame_index: int, fps: float) -> float:
    """Convert a zero-based frame index to a time offset in seconds."""
    if fps <= 0:
        return 0.0
    return frame_index / fps
