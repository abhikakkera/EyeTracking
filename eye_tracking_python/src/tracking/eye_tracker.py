"""
Eye tracker — main orchestrator.

Connects all pipeline stages:
    Camera → FaceDetector → EyeRegionDetector → PupilDetector + IrisDetector
    → BlinkDetector → GazeEstimator → GazeSmoother → MovementAnalyzer
    → FrameRecord → SessionRecorder

Usage:
    tracker = EyeTracker(config)
    tracker.start_session("my_session_id")
    tracker.run(camera)        # blocks; press Q or Esc to stop
    tracker.stop_session()
    session = tracker.session_recorder.current_session
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import numpy as np

from config import AppConfig, SOFTWARE_VERSION
from src.camera.camera_interface import CameraInterface
from src.data.schema import (
    FrameData, FrameQuality, FrameRecord, GazeData,
    SessionMetadata, TestType,
)
from src.detection.blink_detector import BlinkDetector
from src.detection.eye_region_detector import EyeRegionDetector
from src.detection.face_detector import FaceDetector
from src.detection.iris_detector import IrisDetector
from src.detection.pupil_detector import PupilDetector
from src.tracking.gaze_estimator import GazeEstimator
from src.tracking.movement_analyzer import MovementAnalyzer
from src.tracking.smoothing import GazeSmoother
from src.tracking.calibration import CalibrationProfile
from src.data.session_recorder import SessionRecorder
from src.utils.geometry import image_blur_score
from src.utils.timing import FPSCounter, current_timestamp

logger = logging.getLogger(__name__)

# Quality thresholds
_MIN_CONFIDENCE_GOOD = 0.6
_MIN_CONFIDENCE_QUESTIONABLE = 0.3


class EyeTracker:
    """
    Single-session eye tracker.

    Parameters
    ----------
    config : AppConfig
        Centralised configuration object.
    calibration_profile : CalibrationProfile, optional
        Pre-loaded calibration for screen coordinate mapping.
    """

    def __init__(
        self,
        config: AppConfig,
        calibration_profile: Optional[CalibrationProfile] = None,
    ) -> None:
        self._cfg = config
        self._calibration = calibration_profile

        # --- Detection components --------------------------------------------
        self._face_detector = FaceDetector(config)
        self._eye_region_detector = EyeRegionDetector(config)
        self._left_pupil_detector = PupilDetector(config)
        self._right_pupil_detector = PupilDetector(config)
        self._iris_detector = IrisDetector()
        self._blink_detector = BlinkDetector(config)

        # --- Tracking components ---------------------------------------------
        self._gaze_estimator = GazeEstimator()
        self._smoother = GazeSmoother(config)
        self._movement_analyzer = MovementAnalyzer(config)

        # --- Session management ----------------------------------------------
        self.session_recorder = SessionRecorder()
        self._fps_counter = FPSCounter(window=30)
        self._session_id: str = "unstarted"
        self._running = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        session_id: str,
        subject_id: str = "anonymous",
        test_type: TestType = TestType.FREE_VIEWING,
        camera_type: str = "webcam",
    ) -> None:
        """Initialise a new recording session."""
        self._session_id = session_id
        self._blink_detector.set_session_id(session_id)
        self._movement_analyzer.reset(session_id)
        self._left_pupil_detector.reset()
        self._right_pupil_detector.reset()
        self._smoother.reset()
        self._fps_counter.reset()

        metadata = SessionMetadata(
            session_id=session_id,
            subject_id=subject_id,
            timestamp_start=current_timestamp(),
            camera_type=camera_type,
            test_type=test_type,
            calibration_used=self._calibration is not None
            and self._calibration.is_fitted,
            software_version=SOFTWARE_VERSION,
        )
        self.session_recorder.start(metadata)
        logger.info("Session started: %s", session_id)

    def stop_session(self) -> SessionMetadata:
        """Finalise the session and return its metadata."""
        self._running = False
        metadata = self.session_recorder.finish(
            saccades=self._movement_analyzer.saccades,
            fixations=self._movement_analyzer.fixations,
        )
        logger.info(
            "Session ended: %s  frames=%d  saccades=%d  fixations=%d",
            self._session_id,
            metadata.total_frames,
            metadata.saccade_count,
            metadata.fixation_count,
        )
        return metadata

    # ------------------------------------------------------------------
    # Main tracking loop
    # ------------------------------------------------------------------

    def run(
        self,
        camera: CameraInterface,
        on_frame: Optional[Callable[[FrameData, FrameRecord, float], None]] = None,
    ) -> None:
        """
        Blocking tracking loop.  Reads frames until the source is exhausted
        or stop_session() is called externally.

        Parameters
        ----------
        camera   : any CameraInterface implementation
        on_frame : optional callback(frame_data, frame_record, fps) called
                   after each processed frame — use this to draw overlays
                   or check for keyboard events.
        """
        self._running = True
        camera.start()

        try:
            while self._running:
                frame_data = camera.read_frame()
                if frame_data is None:
                    break

                self._fps_counter.tick()
                fps = self._fps_counter.fps

                record = self.process_frame(frame_data)
                self.session_recorder.add_frame(record)

                if on_frame is not None:
                    on_frame(frame_data, record, fps)

        except KeyboardInterrupt:
            logger.info("Tracking interrupted by user.")
        finally:
            camera.stop()
            logger.info("Camera stopped.")

    # ------------------------------------------------------------------
    # Single-frame processing (public — can be called from custom loops)
    # ------------------------------------------------------------------

    def process_frame(self, frame_data: FrameData) -> FrameRecord:
        """
        Run the full detection pipeline on one frame.

        Returns a populated FrameRecord.  Never raises; errors are logged
        and the record is returned with low confidence flags.
        """
        try:
            return self._process_frame_inner(frame_data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in frame %d: %s", frame_data.frame_number, exc)
            return FrameRecord(
                session_id=self._session_id,
                frame_number=frame_data.frame_number,
                timestamp_sec=frame_data.timestamp_sec,
                frame_quality=FrameQuality.BAD,
            )

    def _process_frame_inner(self, frame_data: FrameData) -> FrameRecord:
        img = frame_data.image
        h, w = img.shape[:2]
        t = frame_data.timestamp_sec

        # ---- Face detection -------------------------------------------------
        face = self._face_detector.detect(img)

        record = FrameRecord(
            session_id=self._session_id,
            frame_number=frame_data.frame_number,
            timestamp_sec=t,
            face_detected=face.detected,
        )

        if not face.detected:
            record.frame_quality = FrameQuality.BAD
            return record

        # ---- Eye region extraction ------------------------------------------
        left_eye, right_eye = self._eye_region_detector.extract(img, face)
        record.left_eye_detected = left_eye.detected
        record.right_eye_detected = right_eye.detected
        record.left_ear = left_eye.ear
        record.right_ear = right_eye.ear

        # ---- Pupil detection ------------------------------------------------
        left_pupil = self._left_pupil_detector.detect(left_eye)
        right_pupil = self._right_pupil_detector.detect(right_eye)
        record.left_pupil_detected = left_pupil.detected
        record.right_pupil_detected = right_pupil.detected
        record.left_detection_method = left_pupil.method
        record.right_detection_method = right_pupil.method

        if left_pupil.detected:
            record.left_pupil_x = left_pupil.center_frame[0]
            record.left_pupil_y = left_pupil.center_frame[1]
            record.left_pupil_diameter_px = left_pupil.diameter_px

        if right_pupil.detected:
            record.right_pupil_x = right_pupil.center_frame[0]
            record.right_pupil_y = right_pupil.center_frame[1]
            record.right_pupil_diameter_px = right_pupil.diameter_px

        # ---- Iris detection -------------------------------------------------
        left_iris = self._iris_detector.detect_left(face)
        right_iris = self._iris_detector.detect_right(face)

        # ---- Blink detection ------------------------------------------------
        left_blink_event = self._blink_detector.update("left", left_eye.ear, t)
        right_blink_event = self._blink_detector.update("right", right_eye.ear, t)
        blink_now = (
            self._blink_detector.is_blinking("left")
            or self._blink_detector.is_blinking("right")
        )
        record.blink_detected = blink_now

        if left_blink_event is not None:
            self.session_recorder.add_blink(left_blink_event)
        if right_blink_event is not None:
            self.session_recorder.add_blink(right_blink_event)

        # ---- Gaze estimation ------------------------------------------------
        gaze = self._gaze_estimator.estimate(
            left_eye, right_eye, left_pupil, right_pupil,
            left_iris, right_iris,
        )
        record.left_norm_x, record.left_norm_y = gaze.left_normalized
        record.right_norm_x, record.right_norm_y = gaze.right_normalized
        record.gaze_x, record.gaze_y = gaze.average_normalized

        # ---- Calibration mapping -------------------------------------------
        if self._calibration is not None and self._calibration.is_fitted:
            screen_pos = self._calibration.map_to_screen(gaze.average_normalized)
            if screen_pos is not None:
                record.screen_x, record.screen_y = screen_pos

        # ---- Smoothing -------------------------------------------------------
        if self._cfg.enable_smoothing:
            dt = 1.0 / max(frame_data.fps, 1.0)
            smooth = self._smoother.update((record.gaze_x, record.gaze_y), dt)
            record.smooth_gaze_x, record.smooth_gaze_y = smooth

        # ---- Movement analysis (velocity, saccades, fixations) --------------
        self._movement_analyzer.update(record)

        # ---- Blur / quality assessment --------------------------------------
        import cv2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        record.blur_score = image_blur_score(gray)
        record.confidence_score = self._compute_confidence(record, gaze)
        record.frame_quality = self._classify_quality(record)

        return record

    # ------------------------------------------------------------------
    # Confidence and quality helpers
    # ------------------------------------------------------------------

    def _compute_confidence(self, record: FrameRecord, gaze: GazeData) -> float:
        score = 0.0
        weight = 0.0

        if record.face_detected:
            score += 0.3
        weight += 0.3

        if record.left_eye_detected and record.right_eye_detected:
            score += 0.2
        elif record.left_eye_detected or record.right_eye_detected:
            score += 0.1
        weight += 0.2

        pupil_conf = (
            record.left_pupil_detected * 0.5 +
            record.right_pupil_detected * 0.5
        )
        score += 0.3 * pupil_conf
        weight += 0.3

        if not record.blink_detected:
            score += 0.1
        weight += 0.1

        # Penalise severe blur
        if record.blur_score > 30.0:
            score += 0.1
        weight += 0.1

        return round(score / weight, 3) if weight > 0 else 0.0

    def _classify_quality(self, record: FrameRecord) -> FrameQuality:
        c = record.confidence_score
        if c >= _MIN_CONFIDENCE_GOOD:
            return FrameQuality.GOOD
        if c >= _MIN_CONFIDENCE_QUESTIONABLE:
            return FrameQuality.QUESTIONABLE
        return FrameQuality.BAD

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_fps(self) -> float:
        return self._fps_counter.fps

    def set_calibration(self, profile: CalibrationProfile) -> None:
        self._calibration = profile
        logger.info("Calibration profile attached.")
