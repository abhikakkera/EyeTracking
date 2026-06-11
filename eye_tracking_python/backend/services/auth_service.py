"""
Local authentication for Ocula — password hashing + JWT bearer tokens.

Security posture (LOCAL PROTOTYPE):
  • Passwords are hashed with bcrypt; plaintext is never stored or logged.
  • Tokens are signed JWTs (HS256), valid for 7 days.
  • The signing secret comes from $OCULA_JWT_SECRET, or a per-machine secret
    file under the sessions dir (so tokens survive restarts) — it is NOT a
    production secret-management setup.

This is NOT a production auth system and makes no HIPAA / production-security
claims. It is "good enough" account separation for a local research prototype.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from backend.db import database
from backend.paths import get_sessions_dir

logger = logging.getLogger(__name__)

_ALGO = "HS256"
_TOKEN_TTL_SECONDS = 7 * 24 * 3600
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Raised for signup/login validation failures. Carries an HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Signing secret
# ---------------------------------------------------------------------------

def _get_secret() -> str:
    env = os.environ.get("OCULA_JWT_SECRET")
    if env:
        return env
    secret_file = get_sessions_dir() / ".ocula_jwt_secret"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = secrets.token_hex(32)
    try:
        secret_file.write_text(secret)
        os.chmod(secret_file, 0o600)
    except OSError:
        pass
    return secret


# ---------------------------------------------------------------------------
# Password hashing (bcrypt; never store plaintext)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    # bcrypt caps the input at 72 bytes.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def create_token(user_id: int, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + _TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGO)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, _get_secret(), algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None


def user_id_from_token(token: str) -> Optional[int]:
    payload = decode_token(token)
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public user shaping (never leak password_hash)
# ---------------------------------------------------------------------------

def public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row.get("name") or "",
        "created_at": row.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Signup / login
# ---------------------------------------------------------------------------

def signup(email: str, name: str, password: str) -> Tuple[Dict[str, Any], str]:
    email = (email or "").strip().lower()
    name = (name or "").strip()

    if not _EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if not name:
        raise AuthError("Please enter your name.")
    if database.get_user_by_email(email) is not None:
        raise AuthError("An account with this email already exists.", status=409)

    row = database.create_user(email, name, hash_password(password))
    token = create_token(row["id"], row["email"])
    logger.info("New account created: user_id=%s", row["id"])
    return public_user(row), token


def authenticate(email: str, password: str) -> Tuple[Dict[str, Any], str]:
    email = (email or "").strip().lower()
    row = database.get_user_by_email(email)
    if row is None or not verify_password(password or "", row["password_hash"]):
        # Same message for both cases — don't reveal which accounts exist.
        raise AuthError("Incorrect email or password.", status=401)
    token = create_token(row["id"], row["email"])
    return public_user(row), token
