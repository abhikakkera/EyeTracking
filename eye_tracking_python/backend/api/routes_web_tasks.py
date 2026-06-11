"""
/api/web-sessions routes — the in-browser task mode lifecycle (no OpenCV window).

  POST /api/web-sessions/start            create a session, returns session_id
  POST /api/web-sessions/{id}/event       record a browser task event
  POST /api/web-sessions/{id}/complete    finalize + export + parse results
  POST /api/web-sessions/{id}/cancel      cancel a running session
  GET  /api/web-sessions/{id}/status      poll status

(The frame upload route lives in routes_frame_stream.py.)
"""
from __future__ import annotations

import logging

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user
from backend.db.models import (
    SessionSummary,
    StartWebSessionRequest,
    StartWebSessionResponse,
    WebEventIn,
    WebSessionStatus,
)
from backend.services.web_session_manager import MANAGER, VALID_TASKS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web-sessions", tags=["web-tasks"])


@router.post("/start", response_model=StartWebSessionResponse)
def start_web_session(
    req: StartWebSessionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> StartWebSessionResponse:
    if req.task_type not in VALID_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {req.task_type}")
    session_id = MANAGER.start(
        task_type=req.task_type,
        subject_id=req.participant_id or user.get("name") or "participant",
        screen_w=req.screen_width,
        screen_h=req.screen_height,
        task_config=req.task_config,
        user_id=user["id"],
    )
    return StartWebSessionResponse(session_id=session_id, status="ready")


@router.post("/{session_id}/event")
def record_event(session_id: str, event: WebEventIn) -> dict:
    try:
        MANAGER.add_event(session_id, event.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.post("/{session_id}/complete", response_model=SessionSummary)
def complete_web_session(session_id: str) -> SessionSummary:
    try:
        summary = MANAGER.complete(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SessionSummary(**summary)


@router.post("/{session_id}/cancel", response_model=WebSessionStatus)
def cancel_web_session(session_id: str) -> WebSessionStatus:
    try:
        status = MANAGER.cancel(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return WebSessionStatus(**status)


@router.get("/{session_id}/status", response_model=WebSessionStatus)
def web_session_status(session_id: str) -> WebSessionStatus:
    status = MANAGER.status(session_id)
    return WebSessionStatus(**status)
