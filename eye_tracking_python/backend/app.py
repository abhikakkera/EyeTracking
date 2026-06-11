"""
Ocula backend — FastAPI application.

Run:
    cd eye_tracking_python
    python3 backend/app.py
or:
    uvicorn backend.app:app --reload --port 8000

Two modes are served:
  • CLI/desktop mode  (/api/tests/*)        launches the OpenCV tracker window
  • In-browser web mode (/api/web-sessions/*) renders the stimulus in the
    browser and streams frames here for tracking — NO OpenCV window

All data stays local.

⚠️  Ocula is a research prototype. It does not diagnose, treat, predict, or
    screen for Parkinson's disease or any other medical condition.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the project root importable whether run as `python3 backend/app.py`
# or `uvicorn backend.app:app`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
    routes_auth,
    routes_frame_stream,
    routes_results,
    routes_sessions,
    routes_tests,
    routes_web_tasks,
)
from backend.db.models import WebConfigResponse
from backend.paths import DISCLAIMER, get_db_path, get_sessions_dir
from backend.services import session_store
from config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
)
logger = logging.getLogger("ocula.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    session_store.ensure_db()
    logger.info("Ocula backend ready")
    logger.info("  sessions dir: %s", get_sessions_dir())
    logger.info("  database:     %s", get_db_path())
    yield
    # Shutdown (nothing to clean up — local subprocesses are short-lived)


app = FastAPI(
    title="Ocula Backend",
    version="0.6.0",
    description=(
        "Local backend for the Ocula eye-movement research prototype. "
        + DISCLAIMER
    ),
    lifespan=lifespan,
)

# CORS — allow the local Next.js dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)             # local accounts
app.include_router(routes_tests.router)            # CLI/desktop mode (legacy)
app.include_router(routes_results.router)
app.include_router(routes_sessions.router)
app.include_router(routes_web_tasks.router)        # in-browser web mode
app.include_router(routes_frame_stream.router)     # in-browser frame upload


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "ocula-backend",
        "version": "0.6.0",
        "sessions_dir": str(get_sessions_dir()),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/web-config", response_model=WebConfigResponse, tags=["web-tasks"])
def web_config() -> WebConfigResponse:
    """Advisory capture settings the browser reads before streaming frames."""
    wc = CONFIG.web_capture
    return WebConfigResponse(
        upload_fps=wc.upload_fps,
        jpeg_quality=wc.jpeg_quality,
        max_width=wc.max_width,
        max_height=wc.max_height,
        backend_timeout_ms=wc.backend_timeout_ms,
        stabilization_window_ms=wc.stabilization_window_ms,
        stabilization_min_usable_ratio=wc.stabilization_min_usable_ratio,
        stabilization_min_samples=wc.stabilization_min_samples,
        task_face_loss_warn_ms=wc.task_face_loss_warn_ms,
    )


@app.get("/api/tasks", tags=["health"])
def list_task_types() -> dict:
    """The four supported activities, with friendly names."""
    from backend.services.result_parser import FRIENDLY_NAMES
    return {
        "tasks": [
            {"task_type": k, "activity_name": v}
            for k, v in FRIENDLY_NAMES.items()
        ],
        "disclaimer": DISCLAIMER,
    }


def main() -> None:
    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
