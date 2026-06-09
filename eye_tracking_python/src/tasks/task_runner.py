"""
Task runner — orchestrates camera, eye tracker, and task protocol — v0.3.

Usage:
    runner = TaskRunner(CONFIG)
    task   = ProSaccadeTask(CONFIG)
    session = runner.run(camera, task, subject_id="p01")

The runner owns:
  • Camera start/stop
  • EyeTracker session lifecycle
  • OpenCV stimulus + PIP display
  • Frame-by-frame task context recording
  • Export to task_frames.csv, trials.csv, task_metadata.json

Display layout (single OpenCV window):
  ┌─────────────────────────────────────────────────────────┐
  │  [status bar]  Trial 3/20 | FIXATION | ✓ Good distance │
  │                                                          │
  │               ●   (fixation dot at centre)              │
  │                              ●  (target, if visible)    │
  │                                                          │
  │              [distance guidance bar, top right]          │
  │                                         ┌─────────────┐  │
  │                                         │  PIP camera  │  │
  │                                         │  + overlay   │  │
  │                                         └─────────────┘  │
  │  [task name, bottom-left]     [Q = quit, bottom-right]  │
  └─────────────────────────────────────────────────────────┘

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import AppConfig, SOFTWARE_VERSION
from src.camera.camera_interface import CameraInterface
from src.camera.threaded_stream import ThreadedCameraStream
from src.camera.webcam_stream import WebcamStream
from src.data.schema import TestType
from src.tasks.base_task import BaseTask
from src.tasks.stimulus import StimulusRenderer, StimulusState, _draw_text
from src.tasks.task_analysis import analyze_session
from src.tasks.task_schema import TaskContext, TaskPhase, TaskSession
from src.tracking.eye_tracker import EyeTracker
from src.utils.timing import current_timestamp, FPSCounter
from src.visualization.live_overlay import LiveOverlay

logger = logging.getLogger(__name__)

_QUIT_KEYS = {ord("q"), ord("Q"), 27}


class TaskRunner:
    """
    Connects camera → EyeTracker → BaseTask → display → export.
    """

    def __init__(self, config: AppConfig) -> None:
        self._cfg      = config
        self._renderer = StimulusRenderer()
        self._overlay  = LiveOverlay(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        camera: CameraInterface,
        task: BaseTask,
        subject_id: str = "anonymous",
        out_dir: Optional[str | Path] = None,
        session_id: Optional[str] = None,
    ) -> TaskSession:
        """
        Run one complete task session.

        Parameters
        ----------
        camera     : camera source (WebcamStream or VideoFileStream)
        task       : concrete task instance (e.g. ProSaccadeTask)
        subject_id : participant identifier
        out_dir    : where to write output files (default: config.data.output_dir)

        Returns
        -------
        TaskSession with all frame contexts, completed trials, and analysis.
        """
        out_path = Path(out_dir or self._cfg.data.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # session_id may be supplied by an external caller (e.g. the PDEYE
        # backend) so it knows where the output files will land. Otherwise
        # generate one as before.
        session_id = session_id or str(uuid.uuid4())[:8]
        task._session_id = session_id

        # Wrap camera in background thread
        threaded = ThreadedCameraStream(camera)

        tracker = EyeTracker(self._cfg)
        camera_type = (
            "webcam" if isinstance(camera, WebcamStream)
            else f"video:{getattr(camera, '_path', 'unknown')}"
        )
        tracker.start_session(
            session_id=session_id,
            subject_id=subject_id,
            test_type=task.task_type,
            camera_type=camera_type,
        )

        # Window
        win_name = f"Eye Tracking — {task.task_name}"
        sw = self._cfg.task.screen_width
        sh = self._cfg.task.screen_height
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, sw, sh)
        if self._cfg.task.fullscreen:
            cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN,
                                  cv2.WINDOW_FULLSCREEN)

        all_contexts = []
        fps_counter  = FPSCounter(window=30)
        timestamp_start = current_timestamp()

        threaded.start()
        logger.info("Task session started: %s  type=%s  subject=%s",
                    session_id, task.task_type.value, subject_id)
        print(f"\n[{task.task_name}]  Session {session_id}  |  {task.num_trials} trials")
        print("  Press Q or Esc to stop early.\n")

        try:
            while not task.is_done:
                frame_data = threaded.read_frame()
                if frame_data is None:
                    break

                fps_counter.tick()

                # 1. Eye tracking
                record = tracker.process_frame(frame_data)
                tracker.session_recorder.add_frame(record)

                # 2. Task state machine
                task.on_tracking_frame(record)

                # 3. Collect trial if just completed
                if task.trial_just_completed():
                    trial = task.pop_completed_trial()
                    logger.debug(
                        "Trial %d complete: responded=%s latency=%.0fms",
                        trial.trial_number,
                        trial.response_detected,
                        trial.response_latency_ms,
                    )

                # 4. Record task context for this frame
                ctx = task.current_context()
                ctx.session_id   = session_id
                ctx.frame_number = record.frame_number
                ctx.timestamp_sec = record.timestamp_sec
                all_contexts.append(ctx)

                # 5. Render display
                canvas = self._render_display(
                    sw, sh, task, ctx, frame_data.image, record, fps_counter.fps
                )
                cv2.imshow(win_name, canvas)

                # 6. Quit check
                key = cv2.waitKey(1) & 0xFF
                if key in _QUIT_KEYS:
                    logger.info("Task stopped by user key.")
                    break

        except KeyboardInterrupt:
            logger.info("Task interrupted by Ctrl-C.")
        finally:
            threaded.stop()
            cv2.destroyAllWindows()

        # 7. Finalize tracking
        meta = tracker.stop_session()
        eye_session = tracker.session_recorder.current_session
        timestamp_end = current_timestamp()

        # 8. Analysis
        analysis = analyze_session(
            task.task_type.value,
            task.get_completed_trials(),
        )

        # 9. Build TaskSession
        task_session = TaskSession(
            session_id=session_id,
            task_id=task.task_id,
            task_type=task.task_type.value,
            subject_id=subject_id,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            software_version=SOFTWARE_VERSION,
            task_config_snapshot=self._config_snapshot(),
            task_frames=all_contexts,
            trials=task.get_completed_trials(),
            analysis=analysis,
        )

        # 10. Export
        try:
            from src.data.export_task import export_task_session
            from src.data.export_csv import export_session as export_csv
            from src.data.export_json import export_session as export_json

            if eye_session is not None:
                export_csv(eye_session, out_path)
                export_json(eye_session, out_path)
            export_task_session(task_session, out_path)
            logger.info("Task session exported to %s", out_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Export failed: %s", exc)

        # 11. Print summary
        trials = task.get_completed_trials()
        print(f"\n── {task.task_name} complete ──────────────────────────")
        print(f"  Session:   {session_id}")
        print(f"  Trials:    {len(trials)}/{task.num_trials}")
        print(f"  Frames:    {meta.total_frames}")
        if analysis.get("response_rate") is not None:
            print(f"  Responses: {analysis.get('response_count', 0)}"
                  f"  ({analysis['response_rate']*100:.0f}%)")
        if analysis.get("direction_accuracy") is not None:
            print(f"  Accuracy:  {analysis['direction_accuracy']*100:.0f}%")
        if analysis.get("mean_latency_ms") is not None:
            print(f"  Mean RT:   {analysis['mean_latency_ms']:.0f} ms")
        elif analysis.get("response_count") == 0 and "total_trials" in analysis:
            print("  Mean RT:   N/A (no clear responses detected)")
        if analysis.get("mean_pursuit_gain") is not None:
            print(f"  Pursuit gain: {analysis['mean_pursuit_gain']:.3f}")
        print(f"  Output:    {out_path}/")
        print("─────────────────────────────────────────────────────")

        return task_session

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _render_display(
        self,
        sw: int,
        sh: int,
        task: BaseTask,
        ctx: TaskContext,
        cam_frame: "np.ndarray",
        record,
        fps: float,
    ) -> "np.ndarray":
        cfg = self._cfg.task

        # Build StimulusState from context
        state = StimulusState(
            phase            = ctx.task_phase,
            show_fixation    = ctx.fixation_visible,
            fixation_x       = ctx.fixation_x,
            fixation_y       = ctx.fixation_y,
            fixation_size_px = cfg.fixation_size_px,
            fixation_color   = cfg.fixation_color,
            show_target      = ctx.target_visible,
            target_x         = ctx.target_x,
            target_y         = ctx.target_y,
            target_size_px   = cfg.target_size_px,
            target_color     = cfg.target_color,
            bg_color         = cfg.bg_color,
            trial_text       = (
                f"Trial {ctx.trial_number}/{task.num_trials}"
                if ctx.trial_number > 0 else task.task_name
            ),
            status_text      = ctx.task_phase.value.replace("_", " ").upper(),
        )
        canvas = self._renderer.render(sw, sh, state)

        # Distance guidance bar (top-right)
        dist_status = record.camera_distance_status
        dist_msg    = record.distance_guidance_message
        dist_score  = record.camera_distance_score
        self._renderer.render_distance_overlay(canvas, dist_status, dist_msg, dist_score)

        # PIP camera preview (bottom-right)
        pip_w = int(sw * cfg.pip_width_ratio)
        pip_h = int(pip_w * cam_frame.shape[0] / max(cam_frame.shape[1], 1))
        pip_frame = cv2.resize(cam_frame, (pip_w, pip_h))

        # Annotate PIP with pupil markers
        self._draw_pip_markers(pip_frame, record, pip_w, pip_h,
                               cam_frame.shape[1], cam_frame.shape[0])

        # fps in corner
        _draw_text(pip_frame, f"{fps:.0f} fps", (4, 18),
                   color=(180, 180, 180), scale=0.45)

        # Composite PIP onto canvas (bottom-right, with margin)
        margin = 12
        px = sw - pip_w - margin
        py = sh - pip_h - margin
        canvas[py:py + pip_h, px:px + pip_w] = pip_frame

        # Bottom label
        _draw_text(canvas, task.task_name, (12, sh - 12),
                   color=(120, 120, 120), scale=0.50)
        _draw_text(canvas, "Q / Esc = quit", (sw - 180, sh - 12),
                   color=(100, 100, 100), scale=0.45)

        return canvas

    @staticmethod
    def _draw_pip_markers(
        pip: "np.ndarray",
        record,
        pip_w: int,
        pip_h: int,
        src_w: int,
        src_h: int,
    ) -> None:
        """Draw pupil and gaze markers on the PIP frame (scaled coordinates)."""
        sx = pip_w / max(src_w, 1)
        sy = pip_h / max(src_h, 1)

        if record.left_pupil_detected:
            cv2.circle(pip,
                       (int(record.left_pupil_x * sx), int(record.left_pupil_y * sy)),
                       4, (50, 220, 50), 1)
        if record.right_pupil_detected:
            cv2.circle(pip,
                       (int(record.right_pupil_x * sx), int(record.right_pupil_y * sy)),
                       4, (50, 220, 50), 1)
        if record.face_detected and not record.blink_detected and record.confidence_score > 0.4:
            gx = int(record.gaze_x * pip_w)
            gy = int(record.gaze_y * pip_h)
            cv2.circle(pip, (gx, gy), 6, (200, 200, 30), -1)

    def _config_snapshot(self) -> dict:
        """Serialise TaskConfig to a plain dict for JSON export."""
        cfg = self._cfg.task
        return {
            k: (list(v) if isinstance(v, tuple) else v)
            for k, v in vars(cfg).items()
        }
