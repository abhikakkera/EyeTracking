"""
Logging configuration for the eye tracking system.
Call configure_logging() once at startup; then use get_logger(__name__) everywhere.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """
    Set up the root logger with a console handler and an optional file handler.
    Suppresses noisy third-party libraries.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s  %(levelname)-8s  %(name)-30s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )

    # Suppress chatty libraries
    for lib in ("mediapipe", "matplotlib", "PIL", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Callers should pass __name__."""
    return logging.getLogger(name)
