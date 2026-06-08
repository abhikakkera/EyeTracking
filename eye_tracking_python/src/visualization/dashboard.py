"""
Streamlit analysis dashboard.

Run with:
    cd eye_tracking_python
    streamlit run src/visualization/dashboard.py

This dashboard is for POST-SESSION ANALYSIS of saved CSV/JSON files.
For live tracking, run:   python main.py webcam

⚠️  DISCLAIMER ⚠️
This software is a research prototype for eye-tracking data collection.
It does NOT diagnose, treat, or predict Parkinson's disease or any other
medical condition. Any clinical use requires medical validation, regulatory
review, and oversight by qualified healthcare professionals.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path so imports work when running via streamlit
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    _PLOTLY = True
except ImportError:
    _PLOTLY = False

SESSIONS_DIR = _PROJECT_ROOT / "sessions"


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Eye Tracking Research Dashboard",
    page_icon="👁",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Disclaimer banner
# ---------------------------------------------------------------------------

st.markdown("""
<div style='background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px;margin-bottom:16px;'>
<strong>⚠️ Research Prototype — NOT a Medical Device</strong><br>
This software is for eye-tracking data collection research only.
It does <strong>not</strong> diagnose, treat, or predict Parkinson's disease or any medical condition.
Clinical use requires medical validation, regulatory review, and qualified healthcare supervision.
</div>
""", unsafe_allow_html=True)

st.title("👁 Eye Tracking Research Dashboard")


# ---------------------------------------------------------------------------
# Session selector
# ---------------------------------------------------------------------------

def find_sessions() -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    csvs = sorted(SESSIONS_DIR.glob("*_frames.csv"), reverse=True)
    return csvs


def get_session_id(frames_csv: Path) -> str:
    return frames_csv.stem.replace("_frames", "")


def load_frames(frames_csv: Path) -> pd.DataFrame:
    return pd.read_csv(frames_csv)


def load_metadata(session_id: str) -> dict:
    meta_path = SESSIONS_DIR / f"{session_id}_metadata.json"
    if meta_path.exists():
        with open(meta_path) as fh:
            return json.load(fh)
    return {}


def load_events(session_id: str) -> dict:
    events_path = SESSIONS_DIR / f"{session_id}_events.json"
    if events_path.exists():
        with open(events_path) as fh:
            return json.load(fh)
    return {}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Sessions")
    sessions = find_sessions()

    if not sessions:
        st.info(f"No sessions found in `{SESSIONS_DIR}`.\nRun `python main.py webcam` to record one.")
        st.stop()

    selected_path = st.selectbox(
        "Select session",
        options=sessions,
        format_func=lambda p: get_session_id(p),
    )

    st.markdown("---")
    st.markdown("**Run live tracking:**")
    st.code("python main.py webcam")
    st.code("python main.py video path/to/file.mp4")


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

if selected_path is None:
    st.info("Select a session from the sidebar.")
    st.stop()

session_id = get_session_id(selected_path)

@st.cache_data
def cached_load_frames(path: str) -> pd.DataFrame:
    return load_frames(Path(path))

df = cached_load_frames(str(selected_path))
meta = load_metadata(session_id)
events = load_events(session_id)

# ---------------------------------------------------------------------------
# Metadata summary
# ---------------------------------------------------------------------------

col1, col2, col3, col4, col5 = st.columns(5)

def _stat(col, label, value):
    col.metric(label, value)

_stat(col1, "Total Frames", meta.get("summary", {}).get("total_frames", len(df)))
_stat(col2, "Duration (s)", meta.get("duration_sec", f"{df['timestamp_sec'].max():.1f}"))
_stat(col3, "Saccades", meta.get("summary", {}).get("saccade_count", len(events.get("saccades", []))))
_stat(col4, "Fixations", meta.get("summary", {}).get("fixation_count", len(events.get("fixations", []))))
_stat(col5, "Blinks", meta.get("summary", {}).get("blink_count", len(events.get("blinks", []))))

st.markdown(f"**Session ID:** `{session_id}` &nbsp;|&nbsp; **Type:** {meta.get('test_type', 'unknown')} &nbsp;|&nbsp; **Camera:** {meta.get('camera_type', 'unknown')}")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_gaze, tab_pupil, tab_velocity, tab_events, tab_raw = st.tabs([
    "Gaze Trace", "Pupil Diameter", "Velocity / Saccades", "Events", "Raw Data"
])

# ---- Gaze trace ------------------------------------------------------------
with tab_gaze:
    st.subheader("Gaze Position over Time")
    if _PLOTLY:
        fig = make_subplots(rows=2, cols=1, subplot_titles=["Gaze X", "Gaze Y"], shared_xaxes=True)
        fig.add_trace(go.Scatter(x=df["timestamp_sec"], y=df["gaze_x"],
                                 name="Gaze X (raw)", line=dict(color="steelblue", width=0.8), opacity=0.6), row=1, col=1)
        if "smooth_gaze_x" in df.columns and df["smooth_gaze_x"].notna().any():
            fig.add_trace(go.Scatter(x=df["timestamp_sec"], y=df["smooth_gaze_x"],
                                     name="Gaze X (smooth)", line=dict(color="navy", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["timestamp_sec"], y=df["gaze_y"],
                                 name="Gaze Y (raw)", line=dict(color="salmon", width=0.8), opacity=0.6), row=2, col=1)
        # Shade blinks
        for blink in events.get("blinks", []):
            for r in [1, 2]:
                fig.add_vrect(x0=blink["start_sec"], x1=blink["end_sec"],
                              fillcolor="orange", opacity=0.2, line_width=0, row=r, col=1)
        fig.update_layout(height=400, margin=dict(t=30, b=30))
        st.plotly_chart(fig, use_container_width=True)

        # Scatter
        st.subheader("Gaze Scatter")
        mask = df["face_detected"] == 1
        fig2 = go.Figure(go.Scatter(
            x=df.loc[mask, "gaze_x"],
            y=df.loc[mask, "gaze_y"],
            mode="markers",
            marker=dict(
                size=2,
                color=df.loc[mask, "timestamp_sec"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Time (s)"),
            ),
        ))
        fig2.update_xaxes(range=[0, 1], title="Gaze X")
        fig2.update_yaxes(range=[1, 0], title="Gaze Y", autorange=False)
        fig2.update_layout(height=400, margin=dict(t=10, b=30))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.line_chart(df[["timestamp_sec", "gaze_x", "gaze_y"]].set_index("timestamp_sec"))

# ---- Pupil diameter --------------------------------------------------------
with tab_pupil:
    st.subheader("Pupil Diameter over Time")
    pd_df = df[["timestamp_sec", "left_pupil_diameter_px", "right_pupil_diameter_px"]]
    pd_df = pd_df[(pd_df["left_pupil_diameter_px"] > 0) | (pd_df["right_pupil_diameter_px"] > 0)]
    if _PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pd_df["timestamp_sec"], y=pd_df["left_pupil_diameter_px"],
                                 name="Left", line=dict(color="blue", width=1)))
        fig.add_trace(go.Scatter(x=pd_df["timestamp_sec"], y=pd_df["right_pupil_diameter_px"],
                                 name="Right", line=dict(color="red", width=1)))
        fig.update_layout(height=300, xaxis_title="Time (s)", yaxis_title="Diameter (px)",
                          margin=dict(t=10, b=30))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.line_chart(pd_df.set_index("timestamp_sec"))

    col_a, col_b = st.columns(2)
    col_a.metric("Mean Left PD (px)", f"{pd_df['left_pupil_diameter_px'][pd_df['left_pupil_diameter_px']>0].mean():.1f}")
    col_b.metric("Mean Right PD (px)", f"{pd_df['right_pupil_diameter_px'][pd_df['right_pupil_diameter_px']>0].mean():.1f}")

# ---- Velocity / saccades ---------------------------------------------------
with tab_velocity:
    st.subheader("Gaze Velocity and Saccades")
    if _PLOTLY:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["timestamp_sec"], y=df["gaze_velocity_px_per_sec"],
                                 name="Velocity", line=dict(color="purple", width=1)))
        for sac in events.get("saccades", []):
            fig.add_vrect(x0=sac["start_sec"], x1=sac["end_sec"],
                          fillcolor="red", opacity=0.2, line_width=0)
        fig.update_layout(height=300, xaxis_title="Time (s)", yaxis_title="Velocity (px/s)",
                          margin=dict(t=10, b=30))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.line_chart(df[["timestamp_sec", "gaze_velocity_px_per_sec"]].set_index("timestamp_sec"))

    saccades_list = events.get("saccades", [])
    if saccades_list:
        sac_df = pd.DataFrame(saccades_list)
        st.subheader(f"Saccade Table ({len(sac_df)} events)")
        st.dataframe(sac_df, use_container_width=True)

# ---- Events ----------------------------------------------------------------
with tab_events:
    col_b, col_s, col_f = st.columns(3)
    with col_b:
        st.subheader("Blinks")
        blinks = events.get("blinks", [])
        if blinks:
            st.dataframe(pd.DataFrame(blinks), use_container_width=True)
        else:
            st.info("No blinks recorded.")
    with col_s:
        st.subheader("Saccades")
        sacs = events.get("saccades", [])
        if sacs:
            st.dataframe(pd.DataFrame(sacs)[["start_sec", "duration_ms", "amplitude_px",
                                              "peak_velocity_px_per_sec"]], use_container_width=True)
        else:
            st.info("No saccades recorded.")
    with col_f:
        st.subheader("Fixations")
        fixes = events.get("fixations", [])
        if fixes:
            st.dataframe(pd.DataFrame(fixes), use_container_width=True)
        else:
            st.info("No fixations recorded.")

# ---- Raw data --------------------------------------------------------------
with tab_raw:
    st.subheader("Raw Frame Data")
    st.dataframe(df.head(500), use_container_width=True)
    if meta:
        st.subheader("Session Metadata")
        st.json(meta)

    # Download buttons
    csv_bytes = df.to_csv(index=False).encode()
    st.download_button(
        label="⬇ Download frames CSV",
        data=csv_bytes,
        file_name=f"{session_id}_frames.csv",
        mime="text/csv",
    )
    if meta:
        import json as _json
        st.download_button(
            label="⬇ Download metadata JSON",
            data=_json.dumps(meta, indent=2).encode(),
            file_name=f"{session_id}_metadata.json",
            mime="application/json",
        )
