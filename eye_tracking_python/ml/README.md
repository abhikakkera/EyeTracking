# PDEYE ML — eye-movement screening pipeline (research prototype)

> ⚠️ **Screening aid, not a diagnosis. Not a medical device.**
> This trains/evaluates ML models on eye-movement features **for research only**.
> It does **not** diagnose, treat, predict, or screen for Parkinson's disease or
> any condition. Any real use would need clinically labelled data, ethics (IRB)
> approval, prospective validation, and regulatory review.

This package sits **on top of the tracker's existing exports**. It reads the same
`<id>_blinks.csv`, `<id>_fixations.csv`, and `<id>_trials.csv` files the tracker
already writes, turns each assessment into one interpretable feature vector, and
trains a baseline classifier with **honest, subject-level cross-validation**.

It needs only **numpy / pandas / scikit-learn** — no OpenCV/MediaPipe — so it
installs and runs cleanly on any Python (including 3.13).

## Why this design

* **You have no labelled patient data yet** — and you can't train a real PD
  classifier without it. So the MVP runs the *entire* pipeline on a **synthetic
  cohort** with effects injected on purpose, proving the plumbing works and
  recovers a known signal. Swap in real data later with zero code changes.
* **Webcam-honest features only.** We use signals a 30 FPS webcam can actually
  measure — blink rate, antisaccade error rate, (coarse) saccade latency,
  pursuit gain, gross fixation dispersion. We deliberately **exclude** peak
  saccade velocity, microsaccades, and ocular tremor (below webcam resolution).
  See `schema.EXCLUDED_NOT_WEBCAM_PLAUSIBLE`.
* **Subject-level validation, always.** Labels live with the subject; CV groups
  by subject so no one appears in train and test at once.

## Install

```bash
cd eye_tracking_python
pip install -r ml/requirements.txt
```

## Run the whole thing (synthetic)

```bash
# 1) generate a synthetic cohort (writes tracker-format files + manifest.csv)
python -m ml.simulate --n-control 30 --n-pd 30 --runs 2 --out ml/_synthetic

# 2) train + evaluate the baseline (subject-level CV + leakage demo)
python -m ml.train --data-dir ml/_synthetic --out ml/_artifacts
```

You'll see subject-level AUROC (with a 95% CI), sensitivity / specificity, the
**leakage demo** (how much naive row-level CV inflates the score), and the top
features. Artifacts land in `ml/_artifacts/` (`report.json`, `features.csv`,
`predictions.csv`, `model.joblib`).

## Local web app (no command line)

Everything above, in the browser — generate data, train, see results, and score
one person:

```bash
cd eye_tracking_python
pip install -r ml/requirements.txt
streamlit run ml/app.py        # opens http://localhost:8501
```

## Score one person (research pattern score)

```bash
python -m ml.predict --data-dir ml/_synthetic --battery B00007
```

Outputs a **0–100 PD-pattern similarity score** and a vague band (low/medium/high
similarity to the training "PD" group).

> ⚠️ This score is **not a diagnosis** and **not a probability of disease**. A
> model score only becomes a real disease probability after calibration to the
> condition's base rate; a screening aid flags "maybe look closer", it never
> decides. On synthetic data the score has no clinical meaning at all.

## Run the tests

```bash
cd eye_tracking_python
pytest ml/tests/ -v
```

## Using REAL data later

Nothing in `features.py`/`train.py` knows the data is synthetic. To go real:

1. Collect sessions with the tracker's task modes (`antisaccade`, `prosaccade`,
   `smooth_pursuit`, plus a rest recording for blink rate).
2. Write a `manifest.csv` (see `schema.MANIFEST_FIELDS`) linking each subject's
   session ids to a **label** (from clinical diagnosis) and `age`/`sex`.
3. Run the same two commands above pointed at your real folder.

**Before trusting any number:** age/sex-match your groups, keep every subject's
data on one side of each split, and report confidence intervals — with a handful
of subjects a single AUROC is very noisy.

## Files

| File | Role |
|---|---|
| `schema.py` | Column names + the feature catalogue (rationale + webcam-plausibility) |
| `simulate.py` | Synthetic cohort generator (tracker-format output) |
| `features.py` | Feature extraction from export files (runs on real data unchanged) |
| `dataset.py` | Manifest + features → modelling table (X, y, subject groups) |
| `train.py` | RandomForest baseline, subject-level CV, metrics, leakage demo |
| `tests/` | feature math, simulator, anti-leakage guarantee, end-to-end |

## What's plausible vs. speculative (read before claiming anything)

| Feature | PD direction | Webcam-measurable? |
|---|---|---|
| Blink rate / variability | lower | **yes** |
| Antisaccade error rate | higher | **yes** (strongest signal) |
| Saccade latency (pro/anti) | higher | coarse (±~33 ms) |
| Smooth-pursuit gain / catch-ups | lower / more | coarse |
| Fixation dispersion | higher | weak (only gross instability) |
| Peak saccade velocity | lower | **no** — too few samples at 30 FPS |
| Microsaccades / ocular tremor | altered | **no** — below resolution |
| Pupil diameter (mm) | — | **no** — pixels only, confounded |
