# Ocula — Eye Tracking Research System

**Version 0.4.0 — Research Prototype**

Ocula is a polished local web application layered on top of this Python
eye-tracking engine. It lets you run eye-movement activities **entirely inside a
clean website** — the dots and camera preview are in the browser, frames stream
to the existing Python tracker, and friendly results show up when you finish —
all on your own machine. See
**[Ocula — Web Application Layer](#pdeye--web-application-layer)** below for setup.

---

> ⚠️ **IMPORTANT SAFETY DISCLAIMER**
>
> This software is a **research prototype for eye-tracking data collection only**.
> It does **NOT** diagnose, treat, predict, or screen for Parkinson's disease or any
> other medical condition. Any clinical application would require:
> - Medical validation studies
> - Regulatory approval (FDA, CE, or equivalent)
> - Supervision by qualified healthcare professionals
>
> Do not use this software to make any medical decisions.

---

## What This System Does

A research-grade eye movement tracking platform built in Python. It accurately measures:

| Metric | Description |
|---|---|
| Face position | MediaPipe Face Mesh detection |
| Eye regions | Per-frame left/right eye ROI extraction |
| Pupil centre | Multi-method detection with fallback hierarchy |
| Pupil diameter | Ellipse-fit measurement in pixels |
| Eye movement over time | Frame-by-frame trajectory |
| Gaze direction | Normalised position within each eye box |
| Saccades | Velocity-threshold event detection |
| Fixations | I-DT dispersion-threshold event detection |
| Blinks | Eye Aspect Ratio (EAR) threshold |
| Smooth pursuit | Moving target tracking task |
| Time-series export | CSV, JSON, SQLite |

## Installation

### Prerequisites

- Python 3.11+
- A webcam (built-in laptop camera works for initial testing)
- macOS / Linux / Windows

### Setup

```bash
cd eye_tracking_python

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

## Running the System

### Live Webcam Tracking

```bash
python main.py webcam
```

Press **Q** or **Esc** in the OpenCV window to stop.
Session data is automatically saved to `sessions/`.

### Process a Video File

```bash
python main.py video path/to/recording.mp4
```

### Run Calibration (9-point)

```bash
python main.py calibrate
```

Look at each white dot as it appears. The calibration profile is saved to
`sessions/calibration.json` for future sessions.

### Structured Task Activities (v0.3)

```bash
python main.py task prosaccade        # "Look Toward the Dot"
python main.py task antisaccade       # "Look Away from the Dot"
python main.py task gap_overlap       # "Quick Reaction Dot Task"
python main.py task smooth_pursuit    # "Follow the Moving Dot"

# Options:
python main.py task prosaccade --trials 30 --subject p01
python main.py task smooth_pursuit --pattern circular --cycles 6 --fullscreen
python main.py task gap_overlap --session-id abc12345 --out sessions
```

Each activity writes `<id>_task_metadata.json`, `<id>_trials.csv`,
`<id>_task_frames.csv` plus the standard eye-tracking exports to `sessions/`.

### Smooth Pursuit Task

```bash
python main.py pursuit     # legacy alias for: task smooth_pursuit
```

### Analysis Dashboard

```bash
streamlit run src/visualization/dashboard.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

---

## Ocula — Web Application Layer

Ocula wraps the tracker in a clean, modern website (Next.js) backed by a local
Python API (FastAPI). You start activities in the browser; the backend launches
the existing tracker; results flow back automatically.

> ⚠️ **Ocula is a research prototype for eye-tracking data collection. It does
> not diagnose, treat, predict, or screen for Parkinson's disease or any other
> medical condition. Clinical use would require validation, regulatory review,
> and healthcare professional oversight.**

### What Ocula is

- A polished landing site, activity picker, camera setup, live run screen,
  results pages, and session history.
- A local FastAPI backend that launches `python3 main.py task <type>` and parses
  the output into friendly summaries.
- 100% local: a SQLite store (`sessions/pdeye.db`) for summaries and the existing
  CSV/JSON exports for raw data. No cloud, no accounts.

### Why a backend is required

Browsers cannot launch local Python or open a native camera window for security
reasons. So: **browser → HTTP → FastAPI (trusted local process) → tracker
subprocess**. The browser only calls REST endpoints and polls for completion.

### 1. Install backend dependencies

```bash
cd eye_tracking_python
pip install -r requirements.txt          # tracker engine (if not already)
pip install -r backend/requirements.txt  # fastapi, uvicorn, pydantic, httpx
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
```

### 3. Run the backend (Terminal 1)

```bash
cd eye_tracking_python
python3 backend/app.py
# serves http://127.0.0.1:8000  (health check: /api/health)
```

### 4. Run the website (Terminal 2)

```bash
cd eye_tracking_python/frontend
npm run dev
# open http://localhost:3000
```

The dev server proxies `/api/*` to the backend automatically (see
`next.config.js`). Override with `PDEYE_BACKEND_URL` if needed.

### 5. Start a test from the website

1. Open <http://localhost:3000>
2. Click **Start an Eye Movement Session**
3. Choose an activity (e.g. *Look Toward the Dot*)
4. Complete the quick **camera setup** check, then **Start activity**
5. The tracker window opens — follow the dots
6. When it closes, the website detects completion and shows your **results**
7. Find any run later under **History**

### How results flow back

```
Browser  POST /api/tests/start  ──►  FastAPI  ──►  subprocess: main.py task <type> --session-id <id>
                                                              │ (tracker writes sessions/<id>_*.csv/json)
Browser  GET  /api/tests/status/<id>  (poll)  ◄──  FastAPI detects process exit + result files
                                                              │ parses → stores summary in pdeye.db
Browser  redirect → /results/<id>  ──►  GET /api/results/<id>  ──►  friendly summary JSON
```

### Where results are stored

| Location | Contents |
|---|---|
| `sessions/<id>_task_metadata.json` | Task analysis (latency, accuracy, gain, …) |
| `sessions/<id>_trials.csv` | One row per trial |
| `sessions/<id>_frames.csv` | Per-frame gaze/pupil/quality |
| `sessions/<id>_metadata.json`, `_events.json` | Eye-tracking summary + events |
| `sessions/pdeye.db` | Website session summaries (SQLite, separate from `eye_tracking.db`) |
| `sessions/<id>_report.html` | Optional generated report |

### View previous sessions / export data

- **History page** (`/history`) lists every session with quality and rounds.
- Each result page has download buttons (`/api/results/<id>/download/<kind>`),
  an **Open results folder** button, and a generate-report action.

### In-browser activity mode (v0.5) — no popup window

By default the website now runs the **entire activity inside the browser** — the
dots are drawn on an HTML canvas and the webcam preview is on the page. There is
**no separate OpenCV window**. The browser streams JPEG frames to the backend,
which tracks the eyes with the existing Python pipeline and returns live
guidance.

Flow: `/test` → `/setup?task=…` (intro) → `/run/[taskType]` (camera check →
3-2-1 countdown → full-screen canvas activity) → auto-redirect to
`/results/[sessionId]`.

```
Browser  POST /api/web-sessions/start                       → session_id
Browser  POST /api/web-sessions/{id}/frame   (multipart JPEG + task context, ~12 FPS)
              ◄── { tracking_status, distance_status, guidance_message, gaze… }
Browser  POST /api/web-sessions/{id}/event   (task_started, trial_started, target_shown, …)
Browser  POST /api/web-sessions/{id}/complete
              backend reconstructs trials → writes the SAME exports as CLI mode
              → /results/{id}
```

- Stimulus timing uses the browser's `performance.now()`; every frame carries
  `browser_timestamp_ms` so latencies are accurate.
- Frames are mirrored to screen space, JPEG-compressed, capped in resolution,
  and sent with backpressure (one request in flight) so the UI never freezes.
- Tunables live in `config.py › WebCaptureConfig` (`WEB_FRAME_UPLOAD_FPS`,
  `WEB_FRAME_JPEG_QUALITY`, `WEB_FRAME_MAX_WIDTH/HEIGHT`, `WEB_BACKEND_TIMEOUT_MS`)
  and are served at `GET /api/web-config`.
- **Privacy:** camera frames are processed locally by the backend; raw video is
  not saved (only extracted data + summaries). No cloud, no HIPAA claim.
- The **old CLI/desktop popup mode still works** (`python main.py task …` and the
  `/api/tests/*` routes) — it is untouched.

### API reference (backend)

| Method | Route | Purpose |
|---|---|---|
| GET  | `/api/health` | Liveness check |
| GET  | `/api/tasks` | Supported activities |
| GET  | `/api/web-config` | Browser capture settings |
| **POST** | **`/api/web-sessions/start`** | **Create an in-browser session** |
| **POST** | **`/api/web-sessions/{id}/frame`** | **Upload one webcam frame (multipart)** |
| **POST** | **`/api/web-sessions/{id}/event`** | **Record a browser task event** |
| **POST** | **`/api/web-sessions/{id}/complete`** | **Finalize + export + parse** |
| **POST** | **`/api/web-sessions/{id}/cancel`** | **Cancel an in-browser session** |
| **GET**  | **`/api/web-sessions/{id}/status`** | **Poll frames/events received** |
| POST | `/api/tests/start` | (Legacy) launch the desktop tracker window |
| GET  | `/api/tests/status/{id}` | (Legacy) `preparing｜running｜completed｜failed` |
| POST | `/api/tests/stop/{id}` | (Legacy) cancel a desktop run |
| GET  | `/api/results/latest` | Newest completed summary |
| GET  | `/api/results/{id}` | Friendly summary |
| GET  | `/api/results/{id}/download/{kind}` | Download an export file |
| POST | `/api/results/open-folder` | Open the local results folder |
| GET  | `/api/sessions` | History list |
| GET  | `/api/sessions/{id}` / `/exports` | Single session / its files |

### Data privacy

By default, Ocula stores results **locally on your computer**. Raw eye-tracking
files and session summaries are saved in the local project folder unless you
choose to export them. Cloud syncing is not enabled in this prototype. Ocula does
**not** claim HIPAA compliance or any regulatory certification.

### Limitations / not yet possible

- Webcam-based tracking quality depends on camera, lighting, and distance.
- Frame round-trips run at ~10–15 FPS, so streamed gaze is coarser than the
  30 FPS CLI capture; response detection uses a robust position threshold.
- No on-device calibration yet, so gaze is relative (good for direction/latency,
  not absolute screen coordinates).
- No clinical validation, no medical interpretation, no diagnosis or prognosis.

### Tests

```bash
# Backend (Python) — web mode, CLI mode, parser, store, safety scan
python3 -m pytest tests/test_web_tasks_api.py tests/test_task_event_recorder.py \
                  tests/test_result_parser.py tests/test_session_store.py \
                  tests/test_backend_api.py  tests/test_no_medical_claims.py -v

# Frontend (TypeScript) — task timing, trial generation, API client
cd frontend && npm test
```

The web-mode tests stream real synthetic JPEGs through the tracker — no camera,
no GUI. FastAPI-dependent tests auto-skip if FastAPI isn't installed.
`test_no_medical_claims.py` scans all frontend + backend source for banned
phrases.

---

## Output Files

After each session, the following files appear in `sessions/`:

| File | Contents |
|---|---|
| `<id>_frames.csv` | Per-frame gaze, pupil, blink data |
| `<id>_metadata.json` | Session summary and statistics |
| `<id>_events.json` | Saccade, fixation, and blink events |
| `<id>_trace.png` | Static multi-panel plot |
| `eye_tracking.db` | SQLite database (all sessions) |

## Architecture

```
main.py                     ← CLI entry point
config.py                   ← All parameters in one place
src/
  camera/
    camera_interface.py     ← Abstract base class
    webcam_stream.py        ← OpenCV webcam capture
    video_file_stream.py    ← Pre-recorded video
  detection/
    face_detector.py        ← MediaPipe Face Mesh wrapper
    eye_region_detector.py  ← Eye ROI extraction + EAR
    pupil_detector.py       ← 4-level fallback pupil detection
    iris_detector.py        ← MediaPipe iris landmarks
    blink_detector.py       ← EAR threshold state machine
  tracking/
    eye_tracker.py          ← Main orchestrator
    gaze_estimator.py       ← Normalised gaze computation
    movement_analyzer.py    ← Saccade + fixation detection
    smoothing.py            ← Kalman / EMA / SavGol filters
    calibration.py          ← Screen coordinate mapping
  data/
    schema.py               ← All dataclasses (single source of truth)
    session_recorder.py     ← Session accumulator
    export_csv.py           ← CSV writer
    export_json.py          ← JSON writer
    database.py             ← SQLite store
  visualization/
    live_overlay.py         ← Real-time OpenCV annotations
    trace_plotter.py        ← Matplotlib + Plotly plots
    dashboard.py            ← Streamlit analysis UI
  utils/
    geometry.py             ← EAR, circularity, velocity helpers
    timing.py               ← FPS counter, precision timer
    logging_utils.py        ← Logging setup
tests/
  test_geometry.py
  test_pupil_detector.py
  test_smoothing.py
  test_data_schema.py
```

## Running Tests

```bash
cd eye_tracking_python
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

## Calibration Explained

Without calibration, the system reports normalised gaze within the eye box
(0.0–1.0). After calibration, it can map this to approximate screen pixel
coordinates.

**Calibration process:**
1. 9 targets appear one by one across the screen
2. The system collects 40 frames of pupil data per target
3. A 2nd-degree polynomial regression maps pupil coords → screen coords
4. The profile is saved to `sessions/calibration.json`

Accuracy depends on head stability, lighting, and camera placement.

## Pupil Detection Pipeline

The detector tries four methods in order:

1. **Contour + ellipse fit** — adaptive thresholding, morphological close,
   contour filtering by area/circularity, ellipse fitting
2. **Hough circle transform** — fallback for fragmented contours
3. **Darkest region centroid** — 10th percentile intensity centroid
4. **Temporal prediction** — last known position with very low confidence

## Current Limitations

- Accuracy degrades with glasses (reflections), very dark skin tones in
  poor lighting, and head angles > ~30°
- Pupil diameter is in pixels, not millimetres (requires depth/calibration
  for physical units)
- No head-pose compensation yet
- Calibration is session-specific (head pose changes invalidate it)
- Works best with good frontal lighting and a stable head position

## Configuration

Edit `config.py` to adjust any algorithm parameter:

```python
CONFIG.detection.pupil_min_area_px = 30      # smaller pupils
CONFIG.saccade.velocity_threshold_px_per_sec = 400
CONFIG.blink.ear_closed_threshold = 0.20
CONFIG.smoothing.method = "exponential"       # or "kalman", "savgol"
```

## Future Roadmap

### Infrared Camera Support

Add a new `IRCameraStream(CameraInterface)` class in `src/camera/`. The rest
of the pipeline is camera-agnostic. IR cameras improve tracking in dark
environments and through light-coloured glasses.

### Bluetooth / Mobile Integration

Implement a `NetworkCameraStream` that connects to a phone app streaming
MJPEG or WebRTC. The `CameraInterface` abstraction is the only thing that
needs to change.

### Parkinson's Disease Research Integration

The CSV/JSON exports already include the features relevant to PD research:
- Saccade latency, velocity, amplitude
- Fixation stability and duration
- Smooth pursuit gain and lag
- Blink rate and duration
- Pupil diameter fluctuations
- Micro-movement (tremor proxy via velocity variance)

A future ML pipeline would ingest these feature vectors from many subjects
(both healthy and PD-diagnosed, with clinical ground truth) and train a
validated classifier. **This cannot be done responsibly without:**
- Ethics board approval
- Clinically labelled data
- Prospective validation studies
- Regulatory pathway planning

### Clinical Validation Pipeline

1. Collect data from clinically diagnosed PD cohort and age-matched controls
2. Extract standardised feature vectors using this software
3. Train a binary classifier with cross-validation
4. Validate on an independent held-out cohort
5. Consult neurologists and movement disorder specialists throughout

## License

Research use only. See repository LICENSE file.
