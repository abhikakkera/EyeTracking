"""
/api/web-sessions/{id}/frame — receives one browser webcam frame + task context,
runs it through the Python tracker, and returns live tracking guidance.

The frame is sent as multipart/form-data:
    file : JPEG blob (the captured webcam frame, already mirrored to screen space)
    meta : JSON string with browser_timestamp_ms, task_start_timestamp_ms,
           trial_id, trial_number, task_phase, target_visible, target_x/y,
           target_direction, condition, fixation_visible
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.db.models import FrameResult
from backend.services.web_session_manager import MANAGER

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web-sessions", tags=["web-tasks"])


@router.post("/{session_id}/frame", response_model=FrameResult)
async def upload_frame(
    session_id: str,
    file: UploadFile = File(...),
    meta: str = Form("{}"),
) -> FrameResult:
    try:
        meta_dict = json.loads(meta) if meta else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="meta must be valid JSON")

    data = await file.read()
    try:
        result = MANAGER.process_frame(session_id, data, meta_dict)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return FrameResult(**result)
