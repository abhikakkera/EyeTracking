"""
Eye Tracking System — CLI entry point.

Usage:
    python main.py webcam               # live webcam tracking
    python main.py video path/to/file   # offline video analysis
    python main.py calibrate            # run 9-point calibration
    python main.py pursuit              # smooth pursuit stimulus task

Press  Q  or  Esc  in the OpenCV window to stop.

⚠️  DISCLAIMER ⚠️
This software is a research prototype for eye-tracking data collection.
It does NOT diagnose, treat, or predict any medical condition.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
import uuid
from pathlib import Path

# Ensure the project root is on the path regardless of how main.py is invoked
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import cv2
import numpy as np

from config import CONFIG, SOFTWARE_VERSION
from src.camera.webcam_stream import WebcamStream
from src.camera.video_file_stream import VideoFileStream
from src.data.database import EyeTrackingDatabase
from src.data.export_csv import export_session as export_csv
from src.data.export_json import export_session as export_json
from src.data.schema import TestType
from src.detection.iris_detector import IrisDetector
from src.tracking.calibration import CALIBRATION_9PT, CalibrationCollector, CalibrationProfile
from src.tracking.eye_tracker import EyeTracker
from src.utils.logging_utils import configure_logging, get_logger
from src.visualization.live_overlay import LiveOverlay
from src.visualization.trace_plotter import plot_session_matplotlib

logger = get_logger(__name__)

_WINDOW = "Eye Tracker"
_KEY_QUIT = (ord("q"), ord("Q"), 27)  # Q or Esc


# ---------------------------------------------------------------------------
# Webcam / video tracking
# ---------------------------------------------------------------------------

def run_tracking(
    camera,
    test_type: TestType = TestType.FREE_VIEWING,
    subject_id: str = "anonymous",
) -> None:
    session_id = str(uuid.uuid4())[:8]
    configure_logging(CONFIG.log_level)
    logger.info("Starting tracking  session=%s  type=%s", session_id, test_type.value)

    tracker = EyeTracker(CONFIG)
    overlay = LiveOverlay(CONFIG)
    iris_detector = IrisDetector()

    camera_type = (
        "webcam" if isinstance(camera, WebcamStream)
        else f"video:{getattr(camera, '_path', 'unknown')}"
    )

    tracker.start_session(
        session_id=session_id,
        subject_id=subject_id,
        test_type=test_type,
        camera_type=camera_type,
    )

    cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(_WINDOW, 960, 540)

    def on_frame(frame_data, record, fps):
        # Gather optional data for the overlay
        face = tracker._face_detector.detect(frame_data.image)
        left_iris = iris_detector.detect_left(face)
        right_iris = iris_detector.detect_right(face)

        face_bbox = (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h) if face.detected else None
        left_roi = (
            (record.left_pupil_x - 30, record.left_pupil_y - 20, 60, 40)
            if record.left_pupil_detected else None
        )

        annotated = overlay.draw(
            frame_data.image,
            record,
            fps=fps,
            left_iris=left_iris,
            right_iris=right_iris,
            face_bbox=face_bbox,
        )
        cv2.imshow(_WINDOW, annotated)

        key = cv2.waitKey(1) & 0xFF
        if key in _KEY_QUIT:
            tracker._running = False

    try:
        tracker.run(camera, on_frame=on_frame)
    finally:
        cv2.destroyAllWindows()

    metadata = tracker.stop_session()
    session = tracker.session_recorder.current_session
    if session is None:
        logger.warning("No session data captured.")
        return

    # Export
    out_dir = Path(CONFIG.data.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_files = export_csv(session, out_dir)
    json_files = export_json(session, out_dir)
    logger.info("Exported CSV: %s", [str(p) for p in csv_files])
    logger.info("Exported JSON: %s", [str(p) for p in json_files])

    # Database
    db_path = out_dir / CONFIG.data.db_filename
    db = EyeTrackingDatabase(db_path)
    db.open()
    db.save_session(session)
    db.close()

    # Plot
    plot_session_matplotlib(session, out_dir)

    print(f"\nSession complete: {session_id}")
    print(f"  Frames:    {metadata.total_frames}")
    print(f"  Saccades:  {metadata.saccade_count}")
    print(f"  Fixations: {metadata.fixation_count}")
    print(f"  Blinks:    {metadata.blink_count}")
    print(f"  Output:    {out_dir}/")


# ---------------------------------------------------------------------------
# Calibration routine
# ---------------------------------------------------------------------------

def run_calibration(screen_w: int = 1280, screen_h: int = 720) -> None:
    """
    Interactive 9-point calibration using OpenCV fullscreen window.
    Saves calibration data to sessions/calibration.json.
    """
    camera = WebcamStream(
        device_index=CONFIG.camera.device_index,
        width=CONFIG.camera.resolution[0],
        height=CONFIG.camera.resolution[1],
        target_fps=CONFIG.camera.target_fps,
    )
    camera.start()

    from src.detection.face_detector import FaceDetector
    from src.detection.eye_region_detector import EyeRegionDetector
    from src.detection.pupil_detector import PupilDetector
    from src.tracking.gaze_estimator import GazeEstimator

    face_det = FaceDetector(CONFIG)
    eye_det = EyeRegionDetector(CONFIG)
    left_pd = PupilDetector(CONFIG)
    right_pd = PupilDetector(CONFIG)
    gaze_est = GazeEstimator()
    collector = CalibrationCollector(collect_frames=40)

    calibration_window = "Calibration"
    cv2.namedWindow(calibration_window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(calibration_window, screen_w, screen_h)

    targets = [(int(p[0] * screen_w), int(p[1] * screen_h)) for p in CALIBRATION_9PT]

    for i, (tx, ty) in enumerate(targets):
        # Target screen position (normalised)
        norm_screen = (tx / screen_w, ty / screen_h)
        collector.start_target(norm_screen)

        frames_collected = 0
        print(f"  Calibration point {i+1}/9: look at the dot and hold still...")

        while frames_collected < 40:
            bg = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

            # Shrinking dot animation (visual feedback)
            radius = 20 - int(10 * (frames_collected / 40))
            cv2.circle(bg, (tx, ty), radius + 4, (255, 255, 255), -1)
            cv2.circle(bg, (tx, ty), radius, (0, 120, 255), -1)
            cv2.putText(bg, f"Point {i+1}/9", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 1)

            cv2.imshow(calibration_window, bg)
            cv2.waitKey(1)

            frame = camera.read_frame()
            if frame is None:
                continue

            face = face_det.detect(frame.image)
            if not face.detected:
                continue

            left_eye, right_eye = eye_det.extract(frame.image, face)
            left_pupil = left_pd.detect(left_eye)
            right_pupil = right_pd.detect(right_eye)
            gaze = gaze_est.estimate(left_eye, right_eye, left_pupil, right_pupil)

            if gaze.confidence > 0.3:
                done = collector.add_sample(gaze.average_normalized)
                frames_collected += 1
                if done:
                    break

        avg = collector.finish_target()
        print(f"    Captured pupil avg: {avg}")

        time.sleep(0.3)

    camera.stop()
    cv2.destroyAllWindows()

    if collector.collected_count >= 5:
        profile = collector.build_profile(screen_size=(screen_w, screen_h))
        print(f"\nCalibration fitted with {collector.collected_count} points.")
        Path("sessions").mkdir(exist_ok=True)
        profile.save("sessions/calibration.json")
        print("Saved to sessions/calibration.json")
    else:
        print(f"\nInsufficient calibration data ({collector.collected_count} points). Skipped.")


# ---------------------------------------------------------------------------
# Smooth pursuit task
# ---------------------------------------------------------------------------

def run_smooth_pursuit(
    subject_id: str = "anonymous",
    screen_w: int = 1280,
    screen_h: int = 720,
) -> None:
    """
    Display a moving target and record gaze while the subject tracks it.
    The target follows a sinusoidal horizontal path.
    """
    from src.tracking.eye_tracker import EyeTracker

    session_id = str(uuid.uuid4())[:8]
    camera = WebcamStream(
        device_index=CONFIG.camera.device_index,
        width=CONFIG.camera.resolution[0],
        height=CONFIG.camera.resolution[1],
        target_fps=CONFIG.camera.target_fps,
    )

    tracker = EyeTracker(CONFIG)
    tracker.start_session(
        session_id=session_id,
        subject_id=subject_id,
        test_type=TestType.SMOOTH_PURSUIT,
        camera_type="webcam",
    )

    stimulus_window = "Smooth Pursuit Task"
    cv2.namedWindow(stimulus_window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(stimulus_window, screen_w, screen_h)

    camera.start()
    start_time = time.perf_counter()
    target_positions = []  # (timestamp, tx, ty)

    print("Smooth pursuit task started. Follow the dot. Press Q to stop.")

    try:
        while True:
            elapsed = time.perf_counter() - start_time

            # Target: horizontal sine wave
            freq = 0.3   # Hz
            tx = int(screen_w * 0.5 + screen_w * 0.4 * math.sin(2 * math.pi * freq * elapsed))
            ty = screen_h // 2

            target_positions.append((elapsed, tx / screen_w, ty / screen_h))

            # Draw stimulus
            bg = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            cv2.circle(bg, (tx, ty), 15, (0, 200, 255), -1)
            cv2.circle(bg, (tx, ty), 20, (255, 255, 255), 2)
            cv2.putText(bg, f"Follow the dot  T={elapsed:.1f}s",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
            cv2.imshow(stimulus_window, bg)

            key = cv2.waitKey(1) & 0xFF
            if key in _KEY_QUIT:
                break

            frame = camera.read_frame()
            if frame is None:
                break
            tracker.process_frame(frame)

    finally:
        camera.stop()
        cv2.destroyAllWindows()

    metadata = tracker.stop_session()
    session = tracker.session_recorder.current_session
    if session is None:
        return

    # Append target positions to metadata notes
    session.metadata.notes = f"target_positions_count={len(target_positions)}"

    out_dir = Path(CONFIG.data.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    export_csv(session, out_dir)
    export_json(session, out_dir)
    plot_session_matplotlib(session, out_dir)
    print(f"\nSmooth pursuit session complete: {session_id}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eye_tracker",
        description=(
            f"Eye Tracking Research Prototype v{SOFTWARE_VERSION}\n"
            "NOT a medical device. For research use only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    wc = sub.add_parser("webcam", help="Live webcam tracking")
    wc.add_argument("--subject", default="anonymous", help="Subject identifier")

    vf = sub.add_parser("video", help="Process a video file")
    vf.add_argument("file", help="Path to video file")
    vf.add_argument("--subject", default="anonymous")

    sub.add_parser("calibrate", help="Run 9-point calibration")

    pu = sub.add_parser("pursuit", help="Smooth pursuit stimulus task")
    pu.add_argument("--subject", default="anonymous")

    return p


def main() -> None:
    configure_logging(CONFIG.log_level)
    parser = build_parser()
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Eye Tracking Research System  v{SOFTWARE_VERSION}")
    print("  ⚠️  NOT a medical device. Research use only.")
    print("=" * 60)

    if args.command == "webcam":
        camera = WebcamStream(
            device_index=CONFIG.camera.device_index,
            width=CONFIG.camera.resolution[0],
            height=CONFIG.camera.resolution[1],
            target_fps=CONFIG.camera.target_fps,
        )
        run_tracking(camera, TestType.FREE_VIEWING, subject_id=args.subject)

    elif args.command == "video":
        if not Path(args.file).exists():
            print(f"Error: file not found: {args.file}")
            sys.exit(1)
        camera = VideoFileStream(args.file)
        run_tracking(camera, TestType.VIDEO_ANALYSIS, subject_id=args.subject)

    elif args.command == "calibrate":
        run_calibration()

    elif args.command == "pursuit":
        run_smooth_pursuit(subject_id=args.subject)


if __name__ == "__main__":
    main()
