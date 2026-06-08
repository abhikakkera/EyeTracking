"""
Eye tracker — main orchestrator v0.2.

Bug fixes from v0.1:
  1. Duplicate face detection in on_frame callback is eliminated.
     v0.1: main.py's on_frame() re-called face_detector.detect() on every
     frame without a timestamp_ms. In VIDEO mode MediaPipe requires strictly
     increasing timestamps; the second call (ts=0 by default) violated that
     constraint, corrupting the face-landmarker's internal state for the NEXT
     frame. This cascaded into face_detected=False on nearly every frame,
     causing the session_recorder to count almost all frames as BAD quality
     (good=1 out of 709 frames).
     Fix: save _last_face, _last_left_iris, _last_right_iris after each
     process_frame so the on_frame callback can read cached results instead of
     re-running detection.

  2. frame_quality was computed AFTER movement_analyzer.update().
     v0.1: the movement analyser always saw FrameQuality.GOOD (the dataclass
     default), so quality-filtered saccade/fixation detection never excluded
     bad frames.
     Fix: quality assessment runs at step 11, BEFORE movement_analyzer.update()
     at step 12.

  3. movement_analyzer.flush() was never called at session end.
     v0.1: pending fixations in _fixation_candidates were silently discarded
     when the session ended (fixations=0 even after staring at the screen for
     24 seconds).
     Fix: stop_session() calls self._movement_analyzer.flush() before reading
     .saccades and .fixations.

  4. QualityAssessor wired in — replaces the hand-rolled _compute_confidence
     and _classify_quality helpers with the multi-signal assessor.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

import cv2

from config import AppConfig, SOFTWARE_VERSION
from src.camera.camera_interface import CameraInterface
from src.data.schema import (
    EyeRegionData, FaceData, FrameData, FrameQuality, FrameRecord,
    IrisData, PupilData, SessionMetadata, TestType,
)
from src.detection.blink_detector import BlinkDetector
from src.detection.distance_estimator import DistanceEstimator
from src.detection.eye_region_detector import EyeRegionDetector
from src.detection.face_detector import FaceDetector
from src.detection.iris_detector import IrisDetector
from src.detection.pupil_detector import PupilDetector
from src.detection.quality_assessor import QualityAssessor
from src.tracking.gaze_estimator import GazeEstimator
from src.tracking.movement_analyzer import MovementAnalyzer
from src.tracking.smoothing import GazeSmoother
from src.tracking.calibration import CalibrationProfile
from src.data.session_recorder import SessionRecorder
from src.utils.geometry import image_blur_score
from src.utils.timing import FPSCounter, current_timestamp

logger = logging.getLogger(__name__)


class EyeTracker:
    """
    Single-session eye tracker.

    Parameters
    ----------
    config : AppConfig
    calibration_profile : CalibrationProfile, optional
    """

    def __init__(
        self,
        config: AppConfig,
        calibration_profile: Optional[CalibrationProfile] = None,
    ) -> None:
        self._cfg = config
        self._calibration = calibration_profile

        # Detection components
        self._face_detector = FaceDetector(config)
        self._eye_region_detector = EyeRegionDetector(config)
        self._left_pupil_detector = PupilDetector(config)
        self._right_pupil_detector = PupilDetector(config)
        self._iris_detector = IrisDetector()
        self._blink_detector = BlinkDetector(config)
        self._quality_assessor = QualityAssessor(config)
        self._distance_estimator = DistanceEstimator(config)

        # Tracking components
        self._gaze_estimator = GazeEstimator()
        self._smoother = GazeSmoother(config)
        self._movement_analyzer = MovementAnalyzer(config)

        # Session management
        self.session_recorder = SessionRecorder()
        self._fps_counter = FPSCounter(window=30)
        self._session_id: str = "unstarted"
        self._running = False

        # Cached results from the most recent process_frame() call.
        # The on_frame callback reads these instead of re-calling detect()
        # (re-calling would violate MediaPipe VIDEO-mode timestamp ordering).
        self._last_face: FaceData = FaceData()
        self._last_left_iris: IrisData = IrisData()
        self._last_right_iris: IrisData = IrisData()

        # Previous-frame pupil centre for QualityAssessor jump detection
        self._prev_pupil_center: Optional[Tuple[float, float]] = None

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
        self._session_id = session_id
        self._blink_detector.set_session_id(session_id)
        self._movement_analyzer.reset(session_id)
        self._left_pupil_detector.reset()
        self._right_pupil_detector.reset()
        self._smoother.reset()
        self._fps_counter.reset()
        self._prev_pupil_center = None
        self._distance_estimator.reset()

        metadata = SessionMetadata(
            session_id=session_id,
            subject_id=subject_id,
            timestamp_start=current_timestamp(),
            camera_type=camera_type,
            test_type=test_type,
            calibration_used=(
                self._calibration is not None and self._calibration.is_fitted
            ),
            software_version=SOFTWARE_VERSION,
        )
        self.session_recorder.start(metadata)
        logger.info("Session started: %s", session_id)

    def stop_session(self) -> SessionMetadata:
        """Finalise session. Flushes pending events before reading counts."""
        self._running = False
        # Emit any fixation/saccade still buffered at session end (Bug 3 fix)
        self._movement_analyzer.flush()
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
        Blocking tracking loop.

        Parameters
        ----------
        camera   : CameraInterface implementation
        on_frame : optional callback(frame_data, record, fps) for overlays /
                   keyboard handling. Access self._last_face etc. for cached
                   detection results — do NOT call face_detector.detect() again.
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
    # Single-frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame_data: FrameData) -> FrameRecord:
        """Run the full detection pipeline on one frame. Never raises."""
        try:
            return self._process_frame_inner(frame_data)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unhandled error in frame %d: %s", frame_data.frame_number, exc
            )
            return FrameRecord(
                session_id=self._session_id,
                frame_number=frame_data.frame_number,
                timestamp_sec=frame_data.timestamp_sec,
                frame_quality=FrameQuality.BAD,
                quality_flags=["processing_error"],
            )

    def _process_frame_inner(self, frame_data: FrameData) -> FrameRecord:
        img = frame_data.image
        t = frame_data.timestamp_sec
        timestamp_ms = int(t * 1000)

        # ---- 1. Face detection -----------------------------------------------
        # Pass timestamp_ms so VIDEO-mode MediaPipe gets monotonic timing.
        # The result is cached as _last_face for on_frame callbacks — they must
        # NOT call detect() again (would violate monotonic timestamp rule).
        face = self._face_detector.detect(img, timestamp_ms=timestamp_ms)
        self._last_face = face

        record = FrameRecord(
            session_id=self._session_id,
            frame_number=frame_data.frame_number,
            timestamp_sec=t,
            face_detected=face.detected,
        )

        if not face.detected:
            score, flags, quality = self._quality_assessor.assess(
                face_detected=False,
                left_eye=EyeRegionData(),
                right_eye=EyeRegionData(),
                left_pupil=PupilData(),
                right_pupil=PupilData(),
                blink_detected=False,
            )
            record.confidence_score = score
            record.quality_flags = flags
            record.frame_quality = quality
            # Distance estimator still runs (returns unknown status)
            img_h, img_w = img.shape[:2]
            _dist = self._distance_estimator.assess(
                face, EyeRegionData(), EyeRegionData(), img_w, img_h
            )
            record.camera_distance_status    = _dist.status
            record.camera_distance_score     = _dist.score
            record.distance_guidance_message = _dist.guidance_message
            # No movement to analyze for a face-missing frame
            self._movement_analyzer.update(record)
            return record

        # ---- 2. Eye region extraction ----------------------------------------
        left_eye, right_eye = self._eye_region_detector.extract(img, face)
        record.left_eye_detected = left_eye.detected
        record.right_eye_detected = right_eye.detected
        record.left_ear = left_eye.ear
        record.right_ear = right_eye.ear

        # ---- 2b. Camera distance guidance (v0.3) ----------------------------
        img_h, img_w = img.shape[:2]
        _dist = self._distance_estimator.assess(face, left_eye, right_eye, img_w, img_h)
        record.camera_distance_status  = _dist.status
        record.camera_distance_score   = _dist.score
        record.distance_guidance_message = _dist.guidance_message
        record.face_bbox_width_ratio   = _dist.face_bbox_width_ratio
        record.face_bbox_height_ratio  = _dist.face_bbox_height_ratio
        record.inter_eye_distance_px   = _dist.inter_eye_distance_px

        # ---- 3. Pupil detection ----------------------------------------------
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

        # ---- 4. Iris detection (cached for overlay callback) ----------------
        left_iris = self._iris_detector.detect_left(face)
        right_iris = self._iris_detector.detect_right(face)
        self._last_left_iris = left_iris
        self._last_right_iris = right_iris

        # ---- 5. Blink detection ---------------------------------------------
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

        # ---- 6. Gaze estimation ---------------------------------------------
        gaze = self._gaze_estimator.estimate(
            left_eye, right_eye, left_pupil, right_pupil,
            left_iris, right_iris,
        )
        record.left_norm_x, record.left_norm_y = gaze.left_normalized
        record.right_norm_x, record.right_norm_y = gaze.right_normalized
        record.gaze_x, record.gaze_y = gaze.average_normalized

        # ---- 7. Calibration mapping -----------------------------------------
        if self._calibration is not None and self._calibration.is_fitted:
            screen_pos = self._calibration.map_to_screen(gaze.average_normalized)
            if screen_pos is not None:
                record.screen_x, record.screen_y = screen_pos

        # ---- 8. Smoothing ---------------------------------------------------
        if self._cfg.enable_smoothing:
            dt = 1.0 / max(frame_data.fps, 1.0)
            smooth = self._smoother.update((record.gaze_x, record.gaze_y), dt)
            record.smooth_gaze_x, record.smooth_gaze_y = smooth

        # ---- 9. Frame blur score (full-frame Laplacian variance) -------------
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        record.blur_score = image_blur_score(gray)

        # ---- 10. Pupil centre for unrealistic-jump detection ----------------
        curr_center: Optional[Tuple[float, float]] = None
        if left_pupil.detected and right_pupil.detected:
            curr_center = (
                (left_pupil.center_frame[0] + right_pupil.center_frame[0]) / 2.0,
                (left_pupil.center_frame[1] + right_pupil.center_frame[1]) / 2.0,
            )
        elif left_pupil.detected:
            curr_center = left_pupil.center_frame
        elif right_pupil.detected:
            curr_center = right_pupil.center_frame

        # ---- 11. Quality assessment (BEFORE movement_analyzer — Bug 2 fix) --
        # QualityAssessor sets frame_quality so the movement analyser at step 12
        # can correctly exclude bad/blink frames from saccade/fixation detection.
        score, flags, quality = self._quality_assessor.assess(
            face_detected=face.detected,
            left_eye=left_eye,
            right_eye=right_eye,
            left_pupil=left_pupil,
            right_pupil=right_pupil,
            blink_detected=blink_now,
            prev_center_frame=self._prev_pupil_center,
            current_center_frame=curr_center,
        )
        record.confidence_score = score
        record.quality_flags = flags
        record.frame_quality = quality
        self._prev_pupil_center = curr_center

        # ---- 12. Movement analysis — runs with correct frame_quality ---------
        self._movement_analyzer.update(record)

        return record

    # ------------------------------------------------------------------
    # Properties / helpers
    # ------------------------------------------------------------------

    @property
    def current_fps(self) -> float:
        return self._fps_counter.fps

    def set_calibration(self, profile: CalibrationProfile) -> None:
        self._calibration = profile
        logger.info("Calibration profile attached.")
