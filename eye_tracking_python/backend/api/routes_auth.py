"""
/api/auth routes — local account signup, login, logout, and current user.

Tokens are stateless JWTs, so "logout" is a client-side token drop; the endpoint
exists for symmetry and future revocation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user
from backend.db.models import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UpdateNameRequest,
    UserPublic,
)
from backend.db import database
from backend.services import auth_service, session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
def signup(req: SignupRequest) -> AuthResponse:
    session_store.ensure_db()
    try:
        user, token = auth_service.signup(req.email, req.name, req.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return AuthResponse(token=token, user=UserPublic(**user))


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest) -> AuthResponse:
    session_store.ensure_db()
    try:
        user, token = auth_service.authenticate(req.email, req.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return AuthResponse(token=token, user=UserPublic(**user))


@router.post("/logout")
def logout() -> Dict[str, bool]:
    # Stateless tokens — the client discards it. Endpoint kept for symmetry.
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(user: Dict[str, Any] = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**auth_service.public_user(user))


@router.patch("/me", response_model=UserPublic)
def update_me(
    req: UpdateNameRequest, user: Dict[str, Any] = Depends(get_current_user)
) -> UserPublic:
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    database.update_user_name(user["id"], name)
    fresh = database.get_user_by_id(user["id"])
    return UserPublic(**auth_service.public_user(fresh))
