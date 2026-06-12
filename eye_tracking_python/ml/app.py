"""
PDEYE ML — local web app (Streamlit).

Run it:
    cd eye_tracking_python
    pip install -r ml/requirements.txt
    streamlit run ml/app.py
    # opens http://localhost:8501

Everything the command line does — generate a synthetic cohort, train + evaluate,
and score one person — but in the browser. No data leaves your machine.

⚠️ RESEARCH PROTOTYPE — screening aid, NOT a diagnosis and NOT a medical device.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the project root importable when launched via `streamlit run ml/app.py`.
_ROOT = Path(__file__).resolve().parents[1]   # ml -> eye_tracking_python
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from ml.predict import pattern_band, score_battery
from ml.schema import FEATURE_COLUMNS, FEATURE_INFO
from ml.simulate import CohortConfig, simulate_cohort
from ml.train import run as train_run

DATA_DIR = _ROOT / "ml" / "_synthetic"
ARTIFACTS = _ROOT / "ml" / "_artifacts"

st.set_page_config(page_title="PDEYE ML (research)", page_icon="🧪", layout="wide")

DISCLAIMER = (
    "**Research prototype — screening aid, NOT a diagnosis and NOT a medical "
    "device.** It does not diagnose, treat, predict, or screen for Parkinson's "
    "disease or any condition. Trained on synthetic data; no clinical validation."
)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_report() -> dict | None:
    p = ARTIFACTS / "report.json"
    return json.loads(p.read_text()) if p.exists() else None


def _load_csv(name: str) -> pd.DataFrame | None:
    p = ARTIFACTS / name
    return pd.read_csv(p) if p.exists() else None


def _load_model():
    try:
        import joblib
        p = ARTIFACTS / "model.joblib"
        return joblib.load(p) if p.exists() else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sidebar — generate + train (so nothing needs the command line)
# ---------------------------------------------------------------------------

st.sidebar.title("🧪 PDEYE ML")
st.sidebar.caption("Local research console")

with st.sidebar.form("cohort"):
    st.subheader("1 · Synthetic cohort")
    n_control = st.slider("Controls", 10, 100, 30, 5)
    n_pd = st.slider("PD-like subjects", 10, 100, 30, 5)
    runs = st.slider("Runs per subject", 1, 4, 2)
    severity = st.slider("PD signal strength", 0.5, 2.5, 1.3, 0.1,
                         help="Higher = easier to separate (less overlap).")
    seed = st.number_input("Random seed", 0, 9999, 0)
    go = st.form_submit_button("Generate + Train", type="primary")

if go:
    with st.spinner("Generating synthetic cohort…"):
        simulate_cohort(DATA_DIR, CohortConfig(
            n_control=n_control, n_pd=n_pd, runs_per_subject=runs,
            pd_severity_mean=severity, seed=int(seed)))
    with st.spinner("Training + evaluating (subject-level CV)…"):
        train_run(DATA_DIR, None, ARTIFACTS, model_kind="rf", folds=5,
                  seed=int(seed), demo_leakage=True)
    st.sidebar.success("Done — results below.")

report = _load_report()
preds = _load_csv("predictions.csv")
feats = _load_csv("features.csv")
model = _load_model()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("PDEYE ML — eye-movement pattern analysis")
st.warning(DISCLAIMER)

if report is None:
    st.info("👈 Set the cohort options and click **Generate + Train** to begin.")
    st.stop()

tab_results, tab_person, tab_about = st.tabs(
    ["📊 Cohort results", "🧍 Score one person", "ℹ️ What this means"])


# ---------------------------------------------------------------------------
# Tab: cohort results
# ---------------------------------------------------------------------------

with tab_results:
    g = report["subject_level_cv"]
    ci = g.get("auroc_ci95", [float("nan"), float("nan")])
    c1, c2, c3 = st.columns(3)
    c1.metric("AUROC (subject-level)", f"{g['auroc']:.3f}",
              help="0.5 = coin flip, 1.0 = perfect.")
    c1.caption(f"95% CI [{ci[0]:.3f}, {ci[1]:.3f}]")
    c2.metric("Sensitivity", f"{g['sensitivity']:.0%}")
    c3.metric("Specificity", f"{g['specificity']:.0%}")
    st.caption(f"{report['n_subjects']} subjects · {report['n_batteries']} "
               f"assessments · {report['cv_folds']}-fold subject-level CV")

    if "naive_rowlevel_cv" in report:
        st.subheader("Why we cross-validate by subject (data-leakage demo)")
        gap = report["leakage_auroc_inflation"]
        st.bar_chart(pd.DataFrame({
            "AUROC": [g["auroc"], report["naive_rowlevel_cv"]["auroc"]],
        }, index=["Subject-level (honest)", "Row-level (leaks!)"]))
        st.caption(f"Splitting by row instead of subject inflates AUROC by "
                   f"**{gap:+.3f}** — the model memorises people, not the pattern. "
                   f"The honest number is the lower one.")

    st.subheader("Which features separate the groups")
    sep = pd.DataFrame(report["univariate_separation"]).set_index("feature")
    st.bar_chart(sep["auroc"])
    st.caption("Single-feature separation (AUROC vs label). Directions match the "
               "Parkinson's literature: blink rate ↓, antisaccade errors ↑, pursuit gain ↓.")


# ---------------------------------------------------------------------------
# Tab: per-person score
# ---------------------------------------------------------------------------

with tab_person:
    st.caption("Honest out-of-fold scores: each person was scored by a model that "
               "never trained on them.")
    if preds is None:
        st.info("Train first.")
    else:
        bid = st.selectbox("Pick an assessment", preds["battery_id"].tolist())
        row = preds[preds["battery_id"] == bid].iloc[0]
        score = float(row["pd_pattern_score"])
        band = pattern_band(score)

        col_a, col_b = st.columns([1, 2])
        col_a.metric("PD-pattern score", f"{score * 100:.0f} / 100")
        col_a.progress(min(max(score, 0.0), 1.0))
        col_a.write(f"**{band}**")
        truth = "PD-like" if int(row["label"]) == 1 else "control"
        col_a.caption(f"(synthetic ground truth: {truth})")

        col_b.error(
            "This is a **research pattern score, not a diagnosis** and not a "
            "probability of disease. A screening aid suggests 'maybe look closer'; "
            "it never decides. Synthetic data — no clinical meaning.")

        if feats is not None:
            frow = feats[feats["battery_id"] == bid]
            if len(frow):
                st.subheader("This person's features")
                show = frow[FEATURE_COLUMNS].T.rename(columns={frow.index[0]: "value"})
                st.dataframe(show, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab: about / limitations
# ---------------------------------------------------------------------------

with tab_about:
    st.markdown(
        "### What the score is — and is not\n"
        "- It measures how **similar** one person's eye-movement features are to "
        "the model's *PD-pattern* training group.\n"
        "- It is **not** a diagnosis, and **not** a 'percent chance of Parkinson's'. "
        "Turning a model score into a real disease probability needs calibration "
        "to how common the disease actually is.\n"
        "- Right now everything is **synthetic**, so scores have **no clinical "
        "meaning** — they only prove the pipeline works.\n\n"
        "### Webcam-honest features\n"
        "Only signals a 30 FPS webcam can really measure are used. Peak saccade "
        "velocity, microsaccades, and ocular tremor are **excluded** (below webcam "
        "resolution).")
    st.subheader("Feature reference")
    st.dataframe(pd.DataFrame(
        [{"feature": f.name, "PD direction": f.pd_direction,
          "webcam-measurable": f.plausible, "rationale": f.rationale}
         for f in FEATURE_INFO]),
        use_container_width=True, hide_index=True)
    st.info(DISCLAIMER)
