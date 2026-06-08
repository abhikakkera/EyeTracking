"""
Face detector using the MediaPipe Face Landmarker Tasks API (0.10+).

The legacy mp.solutions.face_mesh API was removed in MediaPipe 0.10.x.
This module uses the new Tasks API: mp.tasks.vision.FaceLandmarker.

The model file (~5 MB) is downloaded automatically to models/ on first run.

Landmark indices are identical to the old solutions API:
    0–467   : face mesh landmarks
    468–472 : right iris (viewer's left / subject's right)
    473–477 : left iris  (viewer's right / subject's left)
"""
from __future__ import annotations

import logging
import ssl
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Tuple

import cv2
import mediapipe as mp
import numpy as np

from config import AppConfig
from src.data.schema import FaceData

logger = logging.getLogger(__name__)

# Viewer-perspective eye landmark groups
VIEWER_LEFT_EYE_LANDMARKS = [
    33, 7, 163, 144, 145, 153, 154, 155, 133,
    173, 157, 158, 159, 160, 161, 246,
]
VIEWER_RIGHT_EYE_LANDMARKS = [
    362, 382, 381, 380, 374, 373, 390, 249, 263,
    466, 388, 387, 386, 385, 384, 398,
]
VIEWER_LEFT_IRIS_CENTER_IDX = 468
VIEWER_RIGHT_IRIS_CENTER_IDX = 473

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent / "models" / "face_landmarker.task"
)


def _ensure_model() -> str:
    """Download the face landmarker model if it is not already cached."""
    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _MODEL_PATH.exists():
        logger.info("Downloading MediaPipe face landmark model (~5 MB) ...")
        _download_file(_MODEL_URL, _MODEL_PATH)
        logger.info("Model saved to %s", _MODEL_PATH)
    return str(_MODEL_PATH)


def _download_file(url: str, dest: Path) -> None:
    """
    Download a file, working around macOS Python SSL certificate issues.
    Tries three methods in order: certifi context → system curl → unverified.
    """
    # Method 1: use certifi if available (cleanest)
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, context=ctx) as r:
            dest.write_bytes(r.read())
        return
    except Exception:
        pass

    # Method 2: use system curl (available on macOS/Linux)
    try:
        subprocess.run(
            ["curl", "-sSL", "-o", str(dest), url],
            check=True,
            timeout=120,
        )
        return
    except Exception:
        pass

    # Method 3: skip SSL verification (last resort — only for model download)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    logger.warning("SSL verification disabled for model download (fallback).")
    with urllib.request.urlopen(url, context=ctx) as r:
        dest.write_bytes(r.read())


class FaceDetector:
    """
    Wraps MediaPipe Face Landmarker to detect the face and all 478 landmarks.

    Usage:
        detector = FaceDetector(config)
        face_data = detector.detect(bgr_frame)
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config.detection
        model_path = _ensure_model()

        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=self._cfg.mediapipe_min_detection_confidence,
            min_face_presence_confidence=self._cfg.mediapipe_min_tracking_confidence,
            min_tracking_confidence=self._cfg.mediapipe_min_tracking_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        logger.info("FaceDetector ready (MediaPipe Tasks API v%s)", mp.__version__)

    def detect(self, bgr_frame: np.ndarray) -> FaceData:
        """
        Run face landmark detection on a BGR frame.

        Returns FaceData with detected=False if no face is found.
        Never raises — errors are caught and logged.
        """
        if bgr_frame is None or bgr_frame.size == 0:
            return FaceData()

        h, w = bgr_frame.shape[:2]

        try:
            rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._landmarker.detect(mp_image)
        except Exception as exc:  # noqa: BLE001
            logger.debug("MediaPipe detection error: %s", exc)
            return FaceData()

        if not result.face_landmarks:
            return FaceData()

        raw_landmarks = result.face_landmarks[0]
        landmarks_px: List[Tuple[float, float]] = [
            (lm.x * w, lm.y * h) for lm in raw_landmarks
        ]

        xs = [p[0] for p in landmarks_px]
        ys = [p[1] for p in landmarks_px]
        bbox_x = int(max(0, min(xs)))
        bbox_y = int(max(0, min(ys)))
        bbox_w = int(min(w, max(xs)) - bbox_x)
        bbox_h = int(min(h, max(ys)) - bbox_y)

        return FaceData(
            detected=True,
            bbox_x=bbox_x,
            bbox_y=bbox_y,
            bbox_w=bbox_w,
            bbox_h=bbox_h,
            landmarks=landmarks_px,
            confidence=0.9,
        )

    def close(self) -> None:
        self._landmarker.close()
