"""
Web session manager — runs the in-browser task mode end to end on the backend.

Per session it owns an EyeTracker (no GUI), accumulates streamed frames + browser
events, and on completion reconstructs trials and writes the SAME export files as
the CLI task mode (so result_parser, the results UI, and history all work).

Thread-safety: each session has its own lock; frame/event/complete calls for one
session are serialized (MediaPipe VIDEO mode needs monotonic, in-order frames).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CONFIG, SOFTWARE_VERSION
from src.data.export_csv import export_session as export_csv
from src.data.export_json import export_session as export_json
from src.data.export_task import export_task_session
from src.data.schema import EyeTestType
from src.tasks.task_analysis import analyze_session
from src.tasks.task_schema import TaskSession
from src.tracking.eye_tracker import EyeTracker

from backend.paths import DISCLAIMER, get_sessions_dir
from backend.services import frame_processor, result_parser, session_store
from backend.services.task_event_recorder import (
    WebFrame,
    build_task_contexts,
    reconstruct_trials,
)

logger = logging.getLogger(__name__)

_TASK_ENUM = {
    "prosaccade": EyeTestType.PROSACCADE,
    "antisaccade": EyeTestType.ANTISACCADE,
    "gap_overlap": EyeTestType.GAP_OVERLAP,
    "smooth_pursuit": EyeTestType.SMOOTH_PURSUIT,
}
VALID_TASKS = set(_TASK_ENUM)


@dataclass
class WebSession:
    session_id: str
    task_id: str
    task_type: str
    subject_id: str
    screen_w: int
    screen_h: int
    task_config: Dict[str, Any]
    tracker: EyeTracker
    lock: threading.Lock = field(default_factory=threading.Lock)
    frames: List[WebFrame] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    status: str = "ready"
    start_wall: float = field(default_factory=time.time)
    task_start_ms: Optional[float] = None
    last_ts_sec: float = 0.0
    frame_count: int = 0
    summary: Optional[Dict[str, Any]] = None


class WebSessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, WebSession] = {}
        self._guard = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        task_type: str,
        subject_id: str,
        screen_w: int,
        screen_h: int,
        task_config: Dict[str, Any],
    ) -> str:
        if task_type not in VALID_TASKS:
            raise ValueError(f"Invalid task_type: {task_type}")

        session_id = uuid.uuid4().hex[:8]
        task_id = uuid.uuid4().hex[:8]

        tracker = EyeTracker(CONFIG)
        tracker.start_session(
            session_id=session_id,
            subject_id=subject_id or "anonymous",
            test_type=_TASK_ENUM[task_type],
            camera_type="web",
        )

        sess = WebSession(
            session_id=session_id,
            task_id=task_id,
            task_type=task_type,
            subject_id=subject_id or "anonymous",
            screen_w=screen_w,
            screen_h=screen_h,
            task_config=task_config or {},
            tracker=tracker,
        )
        with self._guard:
            self._sessions[session_id] = sess

        session_store.record_pending(session_id, task_type, sess.subject_id, status="running")
        logger.info("Web session started: %s (%s)", session_id, task_type)
        return session_id

    def get(self, session_id: str) -> Optional[WebSession]:
        with self._guard:
            return self._sessions.get(session_id)

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------

    def process_frame(self, session_id: str, image_bytes: bytes, meta: Dict[str, Any]) -> Dict[str, Any]:
        sess = self.get(session_id)
        if sess is None:
            raise KeyError(session_id)

        with sess.lock:
            if sess.status in ("completed", "cancelled", "failed"):
                return {
                    "frame_number": sess.frame_count,
                    "tracking_status": "bad",
                    "distance_status": "unknown",
                    "guidance_message": "This session has ended.",
                }
            sess.status = "running"

            if sess.task_start_ms is None:
                sess.task_start_ms = _f(meta.get("task_start_timestamp_ms"))

            img = frame_processor.decode_jpeg(image_bytes)
            frame_number = sess.frame_count
            sess.frame_count += 1

            browser_ts = _f(meta.get("browser_timestamp_ms"), 0.0)
            if sess.task_start_ms:
                ts_sec = max(0.0, (browser_ts - sess.task_start_ms) / 1000.0)
            else:
                ts_sec = frame_number / max(CONFIG.web_capture.upload_fps, 1)
            # Enforce strict monotonicity for MediaPipe VIDEO mode.
            ts_sec = max(ts_sec, sess.last_ts_sec + 1e-3)
            sess.last_ts_sec = ts_sec

            if img is None:
                return {
                    "frame_number": frame_number,
                    "tracking_status": "bad",
                    "distance_status": "unknown",
                    "guidance_message": "Couldn't read that frame — keep facing the camera.",
                    "face_detected": False,
                }

            record = frame_processor.run_tracker(
                sess.tracker, img, frame_number, ts_sec, float(CONFIG.web_capture.upload_fps)
            )
            sess.tracker.session_recorder.add_frame(record)

            sess.frames.append(WebFrame(
                frame_number=frame_number,
                browser_ts_ms=browser_ts,
                server_ts_sec=ts_sec,
                trial_id=str(meta.get("trial_id") or ""),
                trial_number=int(meta.get("trial_number") or -1),
                task_phase=str(meta.get("task_phase") or "waiting"),
                target_visible=bool(meta.get("target_visible")),
                target_x=_f(meta.get("target_x"), 0.5),
                target_y=_f(meta.get("target_y"), 0.5),
                target_direction=str(meta.get("target_direction") or "none"),
                condition=str(meta.get("condition") or "none"),
                fixation_visible=bool(meta.get("fixation_visible")),
                gaze_x=record.gaze_x,
                gaze_y=record.gaze_y,
                face_detected=record.face_detected,
                blink=record.blink_detected,
                confidence=record.confidence_score,
                frame_quality=record.frame_quality.value,
                distance_status=record.camera_distance_status,
                velocity_px_s=record.gaze_velocity_px_per_sec,
            ))

            tracking_status, distance_status, message = frame_processor.live_guidance(record)
            return {
                "frame_number": frame_number,
                "tracking_status": tracking_status,
                "distance_status": distance_status,
                "guidance_message": message,
                "gaze_x": round(record.gaze_x, 4),
                "gaze_y": round(record.gaze_y, 4),
                "confidence": round(record.confidence_score, 3),
                "blink_detected": record.blink_detected,
                "face_detected": record.face_detected,
            }

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def add_event(self, session_id: str, event: Dict[str, Any]) -> None:
        sess = self.get(session_id)
        if sess is None:
            raise KeyError(session_id)
        with sess.lock:
            sess.events.append(event)
            if event.get("type") == "task_started" and sess.task_start_ms is None:
                sess.task_start_ms = _f(event.get("task_start_timestamp_ms") or event.get("timestamp_ms"))

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def complete(self, session_id: str) -> Dict[str, Any]:
        sess = self.get(session_id)
        if sess is None:
            raise KeyError(session_id)

        with sess.lock:
            if sess.status == "completed" and sess.summary:
                return sess.summary
            if sess.frame_count == 0:
                sess.status = "failed"
                session_store.set_status(session_id, "failed")
                raise RuntimeError("No frames were received for this session.")

            out = get_sessions_dir()
            ts_end = time.time()

            # 1. Finalize the eye tracker → frames.csv / metadata.json / events.json
            sess.tracker.stop_session()
            eye_session = sess.tracker.session_recorder.current_session
            if eye_session is not None:
                export_csv(eye_session, out)
                export_json(eye_session, out)

            # 2. Reconstruct trials + task frames from streamed data
            contexts = build_task_contexts(
                session_id, sess.task_id, sess.frames, sess.screen_w, sess.screen_h
            )
            trials = reconstruct_trials(
                sess.task_type, session_id, sess.task_id, sess.frames, sess.events,
                CONFIG.web_capture.response_position_threshold, sess.screen_w, sess.screen_h,
            )
            analysis = analyze_session(sess.task_type, trials)

            task_session = TaskSession(
                session_id=session_id,
                task_id=sess.task_id,
                task_type=sess.task_type,
                subject_id=sess.subject_id,
                timestamp_start=sess.start_wall,
                timestamp_end=ts_end,
                software_version=SOFTWARE_VERSION,
                task_config_snapshot=_serializable(sess.task_config),
                task_frames=contexts,
                trials=trials,
                analysis=analysis,
            )
            # 3. Writes <id>_task_metadata.json, _trials.csv, _task_frames.csv
            export_task_session(task_session, out)

            # 4. Spec-named extra exports (kept alongside the canonical files)
            _write_json(out / f"{session_id}_task_config.json", _serializable(sess.task_config))

            # 5. Parse into the friendly summary + persist + summary_report.json
            summary = result_parser.parse_session(session_id)
            summary["mode"] = "web"
            _write_json(out / f"{session_id}_summary_report.json", summary)
            session_store.save_parsed(summary)

            sess.status = "completed"
            sess.summary = summary
            logger.info("Web session completed: %s (%d frames, %d trials)",
                        session_id, sess.frame_count, len(trials))
            return summary

    def cancel(self, session_id: str) -> Dict[str, Any]:
        sess = self.get(session_id)
        if sess is None:
            raise KeyError(session_id)
        with sess.lock:
            if sess.status not in ("completed", "cancelled"):
                try:
                    sess.tracker.stop_session()
                except Exception:  # noqa: BLE001
                    pass
                sess.status = "cancelled"
                session_store.set_status(session_id, "cancelled")
        return self.status(session_id)

    def status(self, session_id: str) -> Dict[str, Any]:
        sess = self.get(session_id)
        if sess is None:
            return {"session_id": session_id, "status": "not_found",
                    "frames_received": 0, "events_received": 0}
        return {
            "session_id": session_id,
            "status": sess.status,
            "frames_received": sess.frame_count,
            "events_received": len(sess.events),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _serializable(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (d or {}).items():
        out[k] = list(v) if isinstance(v, tuple) else v
    return out


def _write_json(path: Path, doc: Dict[str, Any]) -> None:
    path.write_text(json.dumps(doc, indent=2, default=str))


# Module-level singleton used by the routes.
MANAGER = WebSessionManager()
