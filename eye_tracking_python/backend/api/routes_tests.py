"""
/api/tests routes — start, status, stop a tracker run.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user
from backend.db.models import (
    StartTestRequest,
    StartTestResponse,
    TestStatusResponse,
)
from backend.services import tracker_launcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tests", tags=["tests"])


@router.post("/start", response_model=StartTestResponse)
def start_test(
    req: StartTestRequest, user: Dict[str, Any] = Depends(get_current_user)
) -> StartTestResponse:
    if req.task_type not in tracker_launcher.VALID_TASKS:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {req.task_type}")

    try:
        handle = tracker_launcher.start_run(
            task_type=req.task_type,
            subject_id=req.participant_id or user.get("name") or "participant",
            trials=req.trials,
            pattern=req.pattern,
            cycles=req.cycles,
            user_id=user["id"],
        )
    except RuntimeError as exc:
        # Another session is already running
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return StartTestResponse(
        session_id=handle.session_id,
        status=handle.status,
        task_type=handle.task_type,
        error=handle.error,
    )


@router.get("/status/{session_id}", response_model=TestStatusResponse)
def test_status(session_id: str) -> TestStatusResponse:
    status = tracker_launcher.get_status(session_id)
    return TestStatusResponse(
        session_id=session_id,
        status=str(status.get("status", "not_found")),
        task_type=status.get("task_type"),  # type: ignore[arg-type]
        error=status.get("error"),          # type: ignore[arg-type]
    )


@router.post("/stop/{session_id}", response_model=TestStatusResponse)
def stop_test(session_id: str) -> TestStatusResponse:
    status = tracker_launcher.stop_run(session_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return TestStatusResponse(
        session_id=session_id,
        status=str(status.get("status")),
        task_type=status.get("task_type"),  # type: ignore[arg-type]
        error=status.get("error"),          # type: ignore[arg-type]
    )
