"""
/api/sessions routes — history list, single session, available exports.
All scoped to the logged-in user; users never see each other's sessions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user
from backend.db.models import ExportsResponse, SessionRow, SessionSummary
from backend.services import session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionRow])
def list_sessions(
    limit: int = 100, user: Dict[str, Any] = Depends(get_current_user)
) -> List[SessionRow]:
    rows = session_store.list_summaries(limit=limit, user_id=user["id"])
    return [SessionRow(**r) for r in rows]


@router.get("/{session_id}", response_model=SessionSummary)
def get_session(
    session_id: str, user: Dict[str, Any] = Depends(get_current_user)
) -> SessionSummary:
    if not session_store.owns_session(session_id, user["id"]):
        # 404 (not 403) so session ids can't be probed for existence.
        raise HTTPException(status_code=404, detail="Session not found")
    summary = session_store.get_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionSummary(**summary)


@router.get("/{session_id}/exports", response_model=ExportsResponse)
def get_exports(
    session_id: str, user: Dict[str, Any] = Depends(get_current_user)
) -> ExportsResponse:
    if not session_store.owns_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="No exports found for session")
    exports = session_store.get_exports(session_id)
    if not exports:
        raise HTTPException(status_code=404, detail="No exports found for session")
    return ExportsResponse(session_id=session_id, exports=exports)
