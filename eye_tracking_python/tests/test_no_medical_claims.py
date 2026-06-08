"""
Guardrail test: no banned medical-claim language in user-facing website copy
or backend services, and the approved disclaimer is present.

Scans frontend/src and backend/ source. Does NOT scan this tests/ directory
(which necessarily contains the banned phrases as data).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Phrases that must never appear in user-facing copy.
BANNED = [
    "diagnoses parkinson's",
    "detects parkinson's",
    "parkinson's risk score",
    "you have parkinson's",
    "you do not have parkinson's",
    "medical diagnosis",
    "clinical screening tool",
]

# The approved disclaimer must appear verbatim (normalized) somewhere.
REQUIRED_DISCLAIMER_FRAGMENT = (
    "does not diagnose, treat, predict, or screen for parkinson's disease"
)

SCAN_DIRS = [
    _ROOT / "frontend" / "src",
    _ROOT / "backend",
]
SCAN_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".css", ".py", ".md"}
SKIP_PARTS = {"node_modules", ".next", "__pycache__"}


def _normalize(text: str) -> str:
    """Lowercase and normalize apostrophes / HTML entities for matching."""
    t = text.lower()
    t = t.replace("&apos;", "'").replace("&#39;", "'")
    t = t.replace("’", "'").replace("‘", "'")
    return t


def _iter_files():
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_PARTS for part in p.parts):
                continue
            if p.suffix.lower() in SCAN_SUFFIXES:
                yield p


def test_no_banned_phrases_in_copy():
    offenders = []
    for path in _iter_files():
        text = _normalize(path.read_text(errors="ignore"))
        for phrase in BANNED:
            if phrase in text:
                offenders.append(f"{path.relative_to(_ROOT)} :: '{phrase}'")
    assert not offenders, "Banned medical-claim phrases found:\n" + "\n".join(offenders)


def test_disclaimer_present_in_frontend():
    blob = ""
    for path in _iter_files():
        if "frontend" in path.parts:
            blob += _normalize(path.read_text(errors="ignore"))
    assert REQUIRED_DISCLAIMER_FRAGMENT in blob, (
        "Approved disclaimer fragment not found in frontend copy."
    )


def test_disclaimer_present_in_backend():
    blob = ""
    for path in _iter_files():
        if "backend" in path.parts:
            blob += _normalize(path.read_text(errors="ignore"))
    assert REQUIRED_DISCLAIMER_FRAGMENT in blob, (
        "Approved disclaimer fragment not found in backend copy."
    )
