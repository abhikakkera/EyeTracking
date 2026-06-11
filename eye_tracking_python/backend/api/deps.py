"""
FastAPI auth dependencies.

get_current_user  — requires a valid bearer token; 401 otherwise.
get_optional_user — returns the user if a valid token is present, else None.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException

from backend.db import database
from backend.services import auth_service


def _user_from_header(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    user_id = auth_service.user_id_from_token(token)
    if user_id is None:
        return None
    row = database.get_user_by_id(user_id)
    return row


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    user = _user_from_header(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return user


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[Dict[str, Any]]:
    return _user_from_header(authorization)
