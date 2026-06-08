"""
Abstract camera interface.

Any camera source — webcam, video file, IR camera, phone stream — implements
this interface.  The rest of the system only depends on CameraInterface, making
camera backends swappable without touching tracking code.

Future extensions:
    - BluetoothIRCameraStream   – Bluetooth infrared camera
    - USBIRCameraStream         – USB infrared camera
    - MobileStreamCamera        – network stream from a phone
    - ExternalTrackerAdapter    – wraps dedicated eye-tracking hardware output
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

# Import FrameData here to keep the public API typed.
# Downstream modules import CameraInterface; they receive FrameData objects.
from src.data.schema import FrameData


class CameraInterface(ABC):
    """Base class for all camera / video input sources."""

    @abstractmethod
    def start(self) -> None:
        """Open the camera or video file and prepare for capture."""

    @abstractmethod
    def read_frame(self) -> Optional[FrameData]:
        """
        Read the next frame from the source.

        Returns:
            FrameData if a frame was successfully read.
            None when the source is exhausted (end of file) or on error.
        """

    @abstractmethod
    def stop(self) -> None:
        """Release all resources held by this source."""

    @abstractmethod
    def get_fps(self) -> float:
        """Return the nominal capture rate in frames per second."""

    @abstractmethod
    def get_resolution(self) -> Tuple[int, int]:
        """Return (width, height) in pixels."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """True while the source can produce frames."""
