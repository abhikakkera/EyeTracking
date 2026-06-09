"""
Pydantic request/response models for the PDEYE API.

These define the JSON contract the Next.js frontend consumes (mirrored in
frontend/src/lib/types.ts).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class StartTestRequest(BaseModel):
    task_type: str = Field(..., description="prosaccade | antisaccade | gap_overlap | smooth_pursuit")
    participant_id: Optional[str] = "anonymous"
    mode: str = "guided"
    # Optional overrides forwarded to the tracker CLI
    trials: Optional[int] = None
    pattern: Optional[str] = None     # smooth_pursuit only
    cycles: Optional[int] = None      # smooth_pursuit only


class StartTestResponse(BaseModel):
    session_id: str
    status: str
    task_type: str
    error: Optional[str] = None


class TestStatusResponse(BaseModel):
    session_id: str
    status: str                       # preparing | running | completed | failed | cancelled | not_found
    task_type: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Results / sessions
# ---------------------------------------------------------------------------

class SessionSummary(BaseModel):
    session_id: str
    technical_task_name: str
    activity_name: str
    date_time: Optional[str] = None
    status: str = "completed"
    subject_id: str = "anonymous"
    duration_sec: Optional[float] = None
    fps: Optional[float] = None
    tracking_quality_label: Optional[str] = None
    usable_data_percent: Optional[float] = None
    average_confidence: Optional[float] = None
    blink_count: Optional[int] = None
    rounds_completed: Optional[int] = None
    average_response_time_ms: Optional[float] = None
    task_metrics: Dict[str, Any] = {}
    recommendations: List[str] = []
    exports: Dict[str, str] = {}
    # v0.5: separates tracking quality from task performance, and surfaces
    # frame/trial counts for the developer diagnostics panel.
    diagnostics: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    disclaimer: str


class SessionRow(BaseModel):
    session_id: str
    date_time: Optional[str] = None
    task_type: Optional[str] = None
    activity_name: Optional[str] = None
    status: Optional[str] = None
    tracking_quality_label: Optional[str] = None
    usable_data_percent: Optional[float] = None
    rounds_completed: Optional[int] = None
    average_response_time_ms: Optional[float] = None


class ExportsResponse(BaseModel):
    session_id: str
    exports: Dict[str, str]


class OpenFolderResponse(BaseModel):
    opened: bool
    path: str


# ---------------------------------------------------------------------------
# Web task mode (v0.5) — in-browser stimulus + streamed frames
# ---------------------------------------------------------------------------

class StartWebSessionRequest(BaseModel):
    task_type: str
    participant_id: Optional[str] = "anonymous"
    mode: str = "guided"
    screen_width: int = 1280
    screen_height: int = 720
    # Snapshot of the browser's task config (durations, trial count, etc.)
    task_config: Dict[str, Any] = {}


class StartWebSessionResponse(BaseModel):
    session_id: str
    status: str            # "ready"


class FrameResult(BaseModel):
    frame_number: int
    tracking_status: str           # good | questionable | bad
    distance_status: str           # too_close | too_far | good | unknown
    guidance_message: str
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    confidence: Optional[float] = None
    blink_detected: Optional[bool] = None
    face_detected: Optional[bool] = None


class WebEventIn(BaseModel):
    type: str                      # task_started | trial_started | fixation_shown | ...
    timestamp_ms: float            # browser performance.now()
    trial_id: Optional[str] = None
    trial_number: Optional[int] = None
    direction: Optional[str] = None       # left | right | none
    condition: Optional[str] = None       # gap | overlap | none
    cycle_number: Optional[int] = None
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    task_start_timestamp_ms: Optional[float] = None
    extra: Dict[str, Any] = {}


class WebSessionStatus(BaseModel):
    session_id: str
    status: str                    # ready | running | completed | cancelled | failed | not_found
    frames_received: int = 0
    events_received: int = 0


class WebConfigResponse(BaseModel):
    upload_fps: int
    jpeg_quality: int
    max_width: int
    max_height: int
    backend_timeout_ms: int
