"""
Eye movement trace visualiser.

Produces static and interactive plots from session data:
    • Gaze X/Y over time (time series)
    • Gaze scatter / heatmap
    • Pupil diameter over time
    • Velocity over time with saccade markers
    • Event timeline (blinks, saccades, fixations)

Two backends are supported:
    Matplotlib  — saves to PNG (always available)
    Plotly      — saves interactive HTML (optional; install plotly)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from src.data.session_recorder import SessionData

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")   # headless — no display required
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False


def plot_session_matplotlib(
    session: SessionData,
    output_dir: str | Path,
) -> Optional[Path]:
    """
    Generate a multi-panel summary figure using Matplotlib.
    Saves to <output_dir>/<session_id[:8]>_trace.png.
    Returns the output path, or None if Matplotlib is unavailable.
    """
    if not _MPL_AVAILABLE:
        logger.warning("Matplotlib not available; skipping static plot.")
        return None

    frames = session.frames
    if not frames:
        return None

    ts = np.array([f.timestamp_sec for f in frames])
    gaze_x = np.array([f.gaze_x for f in frames])
    gaze_y = np.array([f.gaze_y for f in frames])
    smooth_x = np.array([f.smooth_gaze_x if f.smooth_gaze_x is not None else f.gaze_x
                         for f in frames])
    smooth_y = np.array([f.smooth_gaze_y if f.smooth_gaze_y is not None else f.gaze_y
                         for f in frames])
    velocity = np.array([f.gaze_velocity_px_per_sec for f in frames])
    pd_left = np.array([f.left_pupil_diameter_px for f in frames])
    pd_right = np.array([f.right_pupil_diameter_px for f in frames])
    blinks = np.array([int(f.blink_detected) for f in frames])
    confidence = np.array([f.confidence_score for f in frames])

    fig = plt.figure(figsize=(14, 10))
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.3)

    # --- Gaze X over time ----------------------------------------------------
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(ts, gaze_x, color="steelblue", lw=0.5, alpha=0.6, label="Raw X")
    ax1.plot(ts, smooth_x, color="navy", lw=1.2, label="Smoothed X")
    ax1.plot(ts, gaze_y, color="salmon", lw=0.5, alpha=0.6, label="Raw Y")
    ax1.plot(ts, smooth_y, color="darkred", lw=1.2, label="Smoothed Y")
    # Shade blink regions
    in_blink = False
    blink_start = 0.0
    for i, b in enumerate(blinks):
        if b and not in_blink:
            blink_start = ts[i]
            in_blink = True
        elif not b and in_blink:
            ax1.axvspan(blink_start, ts[i], alpha=0.15, color="orange")
            in_blink = False
    ax1.set_xlabel("Time (s)", fontsize=8)
    ax1.set_ylabel("Normalised gaze [0-1]", fontsize=8)
    ax1.set_title("Gaze Position over Time", fontsize=9, fontweight="bold")
    ax1.legend(fontsize=7, loc="upper right")
    ax1.set_ylim(0, 1)
    ax1.tick_params(labelsize=7)

    # --- Gaze scatter --------------------------------------------------------
    ax2 = fig.add_subplot(gs[1, 0])
    detected_mask = np.array([f.face_detected and not f.blink_detected for f in frames])
    if detected_mask.any():
        ax2.scatter(gaze_x[detected_mask], gaze_y[detected_mask],
                    c=ts[detected_mask], cmap="viridis", s=0.8, alpha=0.6)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 1)
    ax2.set_ylim(1, 0)
    ax2.set_xlabel("Gaze X", fontsize=8)
    ax2.set_ylabel("Gaze Y", fontsize=8)
    ax2.set_title("Gaze Scatter", fontsize=9, fontweight="bold")
    ax2.set_aspect("equal")
    ax2.tick_params(labelsize=7)

    # --- Pupil diameter over time -------------------------------------------
    ax3 = fig.add_subplot(gs[1, 1])
    valid_pd = pd_left > 0
    ax3.plot(ts[valid_pd], pd_left[valid_pd], color="blue", lw=0.8,
             label="Left", alpha=0.8)
    valid_pd_r = pd_right > 0
    ax3.plot(ts[valid_pd_r], pd_right[valid_pd_r], color="red", lw=0.8,
             label="Right", alpha=0.8)
    ax3.set_xlabel("Time (s)", fontsize=8)
    ax3.set_ylabel("Diameter (px)", fontsize=8)
    ax3.set_title("Pupil Diameter", fontsize=9, fontweight="bold")
    ax3.legend(fontsize=7)
    ax3.tick_params(labelsize=7)

    # --- Velocity with saccade markers --------------------------------------
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.plot(ts, velocity, color="purple", lw=0.6, alpha=0.8, label="Velocity")
    for sac in session.saccades:
        ax4.axvspan(sac.start_timestamp_sec, sac.end_timestamp_sec,
                    alpha=0.3, color="red")
    ax4.set_xlabel("Time (s)", fontsize=8)
    ax4.set_ylabel("Velocity (px/s)", fontsize=8)
    ax4.set_title("Gaze Velocity + Saccades (red)", fontsize=9, fontweight="bold")
    ax4.tick_params(labelsize=7)

    # --- Confidence over time -----------------------------------------------
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.fill_between(ts, confidence, alpha=0.5, color="teal")
    ax5.set_ylim(0, 1)
    ax5.set_xlabel("Time (s)", fontsize=8)
    ax5.set_ylabel("Confidence", fontsize=8)
    ax5.set_title("Detection Confidence", fontsize=9, fontweight="bold")
    ax5.tick_params(labelsize=7)

    # --- Title ---------------------------------------------------------------
    sid = session.metadata.session_id[:8]
    fig.suptitle(
        f"Eye Tracking Session  {sid}  |  {session.metadata.test_type.value}",
        fontsize=11, fontweight="bold",
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{sid}_trace.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Trace plot saved: %s", path)
    return path


def plot_session_plotly(
    session: SessionData,
    output_dir: str | Path,
) -> Optional[Path]:
    """
    Generate an interactive HTML figure using Plotly.
    Returns None if Plotly is not installed.
    """
    if not _PLOTLY_AVAILABLE:
        logger.warning("Plotly not installed; skipping interactive plot. pip install plotly")
        return None

    frames = session.frames
    if not frames:
        return None

    ts = [f.timestamp_sec for f in frames]
    gaze_x = [f.gaze_x for f in frames]
    gaze_y = [f.gaze_y for f in frames]
    smooth_x = [f.smooth_gaze_x or f.gaze_x for f in frames]
    velocity = [f.gaze_velocity_px_per_sec for f in frames]
    pd_left = [f.left_pupil_diameter_px for f in frames]

    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=["Gaze X/Y over Time", "Velocity", "Pupil Diameter (Left)"],
        shared_xaxes=True,
    )
    fig.add_trace(go.Scatter(x=ts, y=gaze_x, name="Gaze X (raw)",
                             line=dict(color="steelblue", width=1), opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=ts, y=smooth_x, name="Gaze X (smooth)",
                             line=dict(color="navy", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=ts, y=gaze_y, name="Gaze Y (raw)",
                             line=dict(color="salmon", width=1), opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=ts, y=velocity, name="Velocity",
                             line=dict(color="purple", width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=ts, y=pd_left, name="PD Left",
                             line=dict(color="blue", width=1)), row=3, col=1)

    # Saccade shading
    for sac in session.saccades:
        for row in [1, 2, 3]:
            fig.add_vrect(
                x0=sac.start_timestamp_sec, x1=sac.end_timestamp_sec,
                fillcolor="red", opacity=0.15, line_width=0, row=row, col=1,
            )

    fig.update_layout(
        title=f"Eye Tracking  {session.metadata.session_id[:8]}",
        height=700,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sid = session.metadata.session_id[:8]
    path = out / f"{sid}_trace.html"
    fig.write_html(str(path))
    logger.info("Interactive plot saved: %s", path)
    return path
