# Eye Tracking Research System

**Version 0.1.0 — Research Prototype**

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

### Smooth Pursuit Task

```bash
python main.py pursuit
```

Follow the moving dot with your eyes.

### Analysis Dashboard

```bash
streamlit run src/visualization/dashboard.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

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
