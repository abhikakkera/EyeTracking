"""
/api/results routes — latest result, specific result, downloads, open folder.
All session reads are scoped to the logged-in user.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.api.deps import get_current_user
from backend.db import database
from backend.db.models import OpenFolderResponse, SessionSummary
from backend.paths import get_sessions_dir
from backend.services import report_service, result_parser, session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/results", tags=["results"])

_DOWNLOAD_KINDS = {
    "trials": "trials", "frames": "frames", "events": "events",
    "task_metadata": "task_metadata", "metadata": "metadata",
    "task_frames": "task_frames", "saccades": "saccades",
    "fixations": "fixations", "blinks": "blinks",
}


@router.get("/latest", response_model=SessionSummary)
def latest_result(user: Dict[str, Any] = Depends(get_current_user)) -> SessionSummary:
    sid = database.latest_completed_session_id(user_id=user["id"])
    if sid is None:
        raise HTTPException(status_code=404, detail="No completed sessions yet")
    summary = session_store.get_summary(sid)
    if summary is None:
        raise HTTPException(status_code=404, detail="Could not load latest session")
    return SessionSummary(**summary)


@router.get("/{session_id}", response_model=SessionSummary)
def get_result(
    session_id: str, user: Dict[str, Any] = Depends(get_current_user)
) -> SessionSummary:
    if not session_store.owns_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    summary = session_store.get_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionSummary(**summary)


@router.get("/{session_id}/download/{kind}")
def download_export(
    session_id: str, kind: str, user: Dict[str, Any] = Depends(get_current_user)
):
    if not session_store.owns_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    key = _DOWNLOAD_KINDS.get(kind)
    if key is None:
        raise HTTPException(status_code=400, detail=f"Unknown export kind: {kind}")
    files = result_parser.session_files(session_id)
    path = files[key]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Export not found: {kind}")
    return FileResponse(str(path), filename=path.name)


@router.post("/{session_id}/report")
def make_report(
    session_id: str, user: Dict[str, Any] = Depends(get_current_user)
):
    if not session_store.owns_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    summary = session_store.get_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    path = report_service.build_html_report(summary)
    summary["html_report_path"] = str(path)
    session_store.save_parsed(summary)
    return {"session_id": session_id, "html_report_path": str(path)}


@router.post("/open-folder", response_model=OpenFolderResponse)
def open_folder(user: Dict[str, Any] = Depends(get_current_user)) -> OpenFolderResponse:
    path = str(get_sessions_dir())
    opened = report_service.open_results_folder()
    return OpenFolderResponse(opened=opened, path=path)
