"""
Brand + safety guardrails for the website copy.

  • The product is named "Ocula" — "PDEYE" must not appear in user-facing files.
  • The approved disclaimer text is present.
  • No banned medical claims appear in user-facing website copy.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND = _ROOT / "frontend" / "src"

_EXACT_DISCLAIMER = (
    "This software is a research prototype for eye-tracking data collection. "
    "It does not diagnose, treat, predict, or screen for Parkinson's disease "
    "or any other medical condition. Clinical use would require validation, "
    "regulatory review, and healthcare professional oversight."
)

# Phrases that must never appear in user-facing copy.
_BANNED = [
    "diagnoses parkinson",
    "detects parkinson",
    "parkinson's risk score",
    "parkinsons risk score",
    "you have parkinson",
    "you do not have parkinson",
    "medical diagnosis",
    "clinical screening tool",
    "risk score",
]


def _frontend_files():
    return [p for p in _FRONTEND.rglob("*") if p.suffix in (".ts", ".tsx") and p.is_file()]


def test_no_pdeye_in_frontend():
    offenders = []
    for f in _frontend_files():
        if "PDEYE" in f.read_text():
            offenders.append(str(f.relative_to(_ROOT)))
    assert not offenders, f"'PDEYE' still present in user-facing files: {offenders}"


def test_ocula_brand_present():
    blob = "\n".join(f.read_text() for f in _frontend_files())
    assert "Ocula" in blob
    # Brand appears in the navbar and the page metadata
    assert "Ocula" in (_FRONTEND / "components" / "Navbar.tsx").read_text()
    assert "Ocula" in (_FRONTEND / "app" / "layout.tsx").read_text()


def test_exact_disclaimer_present():
    constants = (_FRONTEND / "lib" / "constants.ts").read_text()
    # Normalise whitespace across the JS string concatenation.
    norm = re.sub(r'"\s*\+\s*"', "", constants)
    norm = re.sub(r"\s+", " ", norm)
    assert _EXACT_DISCLAIMER in norm


def test_no_banned_medical_claims_in_frontend():
    offenders = []
    for f in _frontend_files():
        low = f.read_text().lower()
        for phrase in _BANNED:
            if phrase in low:
                offenders.append((str(f.relative_to(_ROOT)), phrase))
    assert not offenders, f"Banned medical phrasing found: {offenders}"
