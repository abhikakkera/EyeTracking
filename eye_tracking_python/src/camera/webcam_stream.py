"""
Webcam implementation of CameraInterface using OpenCV VideoCapture.

To swap to an infrared camera, change device_index or pass a custom
capture URI (e.g., 'rtsp://...' or a V4L2 path like '/dev/video2').
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import cv2

from src.camera.camera_interface import CameraInterface
from src.data.schema import FrameData
from src.utils.timing import PrecisionTimer, current_timestamp

logger = logging.getLogger(__name__)


class WebcamStream(CameraInterface):
    """
    Captures frames from a local webcam (or any OpenCV-compatible device).

    Parameters
    ----------
    device_index : int or str
        OpenCV capture index (0 = default webcam) or a URI string.
    width, height : int
        Requested capture resolution. The camera may select the nearest
        supported mode; check get_resolution() after start().
    target_fps : int
        Requested frame rate. Actual rate depends on the hardware.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1280,
        height: int = 720,
        target_fps: int = 30,
    ) -> None:
        self._device_index = device_index
        self._width = width
        self._height = height
        self._target_fps = target_fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_number: int = 0
        self._session_timer = PrecisionTimer()
        self._actual_fps: float = float(target_fps)

    # ------------------------------------------------------------------
    # CameraInterface implementation
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info("Opening webcam device %s", self._device_index)
        self._cap = cv2.VideoCapture(self._device_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera device {self._device_index}. "
                "Check that no other process is using it."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
        # Minimise internal buffer to reduce real-time lag
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Read actual resolution back from the driver
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._actual_fps = self._cap.get(cv2.CAP_PROP_FPS) or float(self._target_fps)

        self._frame_number = 0
        self._session_timer.start()
        logger.info(
            "Webcam opened: %dx%d @ %.1f fps",
            self._width, self._height, self._actual_fps,
        )

    def read_frame(self) -> Optional[FrameData]:
        if self._cap is None or not self._cap.isOpened():
            return None

        ret, image = self._cap.read()
        if not ret or image is None:
            logger.warning("Webcam read failed (frame %d)", self._frame_number)
            return None

        timestamp = self._session_timer.elapsed_seconds()
        wall = current_timestamp()
        frame = FrameData(
            image=image,
            frame_number=self._frame_number,
            timestamp_sec=timestamp,
            wall_clock=wall,
            fps=self._actual_fps,
            width=image.shape[1],
            height=image.shape[0],
            source="webcam",
        )
        self._frame_number += 1
        return frame

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Webcam released after %d frames", self._frame_number)

    def get_fps(self) -> float:
        return self._actual_fps

    def get_resolution(self) -> Tuple[int, int]:
        return (self._width, self._height)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
