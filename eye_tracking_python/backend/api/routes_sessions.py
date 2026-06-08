"""
/api/sessions routes — history list, single session, available exports.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from backend.db.models import ExportsResponse, SessionRow, SessionSummary
from backend.services import session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionRow])
def list_sessions(limit: int = 100) -> List[SessionRow]:
    rows = session_store.list_summaries(limit=limit)
    return [SessionRow(**r) for r in rows]


@router.get("/{session_id}", response_model=SessionSummary)
def get_session(session_id: str) -> SessionSummary:
    summary = session_store.get_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionSummary(**summary)


@router.get("/{session_id}/exports", response_model=ExportsResponse)
def get_exports(session_id: str) -> ExportsResponse:
    exports = session_store.get_exports(session_id)
    if not exports:
        raise HTTPException(status_code=404, detail="No exports found for session")
    return ExportsResponse(session_id=session_id, exports=exports)
