"""
Video file implementation of CameraInterface.

Processes a saved video exactly as the webcam path would — including realistic
per-frame timestamps derived from the video's FPS — so offline analysis
produces numerically identical results to live tracking.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2

from src.camera.camera_interface import CameraInterface
from src.data.schema import FrameData
from src.utils.timing import current_timestamp, frame_index_to_seconds

logger = logging.getLogger(__name__)


class VideoFileStream(CameraInterface):
    """
    Reads frames from a pre-recorded video file.

    Parameters
    ----------
    file_path : str | Path
        Path to the video file (e.g. .mp4, .avi, .mov, .mkv).
    loop : bool
        If True the video restarts after the last frame. Useful for demos.
    """

    def __init__(self, file_path: str | Path, loop: bool = False) -> None:
        self._path = Path(file_path)
        self._loop = loop
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_number: int = 0
        self._fps: float = 30.0
        self._width: int = 0
        self._height: int = 0
        self._total_frames: int = 0

    # ------------------------------------------------------------------
    # CameraInterface implementation
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Video file not found: {self._path}")

        logger.info("Opening video file: %s", self._path)
        self._cap = cv2.VideoCapture(str(self._path))
        if not self._cap.isOpened():
            raise RuntimeError(f"OpenCV cannot open video: {self._path}")

        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._frame_number = 0

        logger.info(
            "Video: %dx%d  %.2f fps  %d frames  (%.1f s)",
            self._width, self._height, self._fps,
            self._total_frames, self._total_frames / max(self._fps, 1),
        )

    def read_frame(self) -> Optional[FrameData]:
        if self._cap is None or not self._cap.isOpened():
            return None

        ret, image = self._cap.read()
        if not ret or image is None:
            if self._loop:
                logger.debug("Video looping back to frame 0")
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._frame_number = 0
                ret, image = self._cap.read()
                if not ret or image is None:
                    return None
            else:
                logger.info("Video file exhausted at frame %d", self._frame_number)
                return None

        # Compute timestamp from frame index so analysis is timing-accurate
        timestamp = frame_index_to_seconds(self._frame_number, self._fps)
        frame = FrameData(
            image=image,
            frame_number=self._frame_number,
            timestamp_sec=timestamp,
            wall_clock=current_timestamp(),
            fps=self._fps,
            width=image.shape[1],
            height=image.shape[0],
            source=str(self._path),
        )
        self._frame_number += 1
        return frame

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info(
                "Video released: processed %d / %d frames",
                self._frame_number, self._total_frames,
            )

    def get_fps(self) -> float:
        return self._fps

    def get_resolution(self) -> Tuple[int, int]:
        return (self._width, self._height)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def progress(self) -> float:
        """Return processing progress as a fraction in [0, 1]."""
        if self._total_frames <= 0:
            return 0.0
        return self._frame_number / self._total_frames
