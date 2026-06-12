"""
Synthetic cohort generator.

Writes eye-tracking session files in the SAME format the real tracker exports,
so the feature/training code is exercised on realistic inputs and will run
unchanged on real data later.

Design choices that matter scientifically
------------------------------------------
* Each subject gets a single latent ``severity`` scalar, drawn once. ALL of that
  subject's runs share it, so their feature rows are correlated — this is exactly
  why you must cross-validate by SUBJECT, not by row. (See ``train.py`` leakage demo.)
* Group effects are injected ONLY into webcam-plausible signals (blink rate,
  antisaccade error rate, saccade latency, pursuit gain, fixation dispersion),
  with heavy overlap between groups. Nothing depends on peak velocity,
  microsaccades, or ocular tremor — a webcam cannot see those.
* Age and sex are drawn independently of label (matched cohort) to avoid baking
  in a confound. Real data must likewise be age/sex-matched.

⚠️ This is SIMULATED data with INVENTED effect sizes. It demonstrates that the
pipeline works end-to-end and recovers a signal that was put there on purpose.
It says NOTHING about real Parkinson's disease.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.schema import (
    BLINK_FIELDS,
    FIXATION_FIELDS,
    FRAME_FIELDS,
    MANIFEST_FIELDS,
    PURSUIT_TRIAL_FIELDS,
    SACCADE_TRIAL_FIELDS,
)

_DISCLAIMER = (
    "SYNTHETIC research data. Not real subjects. This software does not diagnose, "
    "treat, predict, or screen for Parkinson's disease or any medical condition."
)


@dataclass
class CohortConfig:
    n_control: int = 25
    n_pd: int = 25
    runs_per_subject: int = 2
    fps: float = 30.0
    rest_duration_sec: float = 60.0
    antisaccade_trials: int = 24
    prosaccade_trials: int = 24
    pursuit_cycles: int = 10
    fixations_per_rest: int = 12
    # Latent severity: control ~ N(0, 1), PD ~ N(pd_severity_mean, 1). Overlap is
    # intentional — real groups overlap heavily on any single feature.
    pd_severity_mean: float = 1.3
    seed: int = 0


# ---------------------------------------------------------------------------
# Latent severity -> target feature levels for one run
# ---------------------------------------------------------------------------

def _targets_for_run(severity: float, rng: np.random.Generator) -> dict:
    """Map a subject's latent severity (+ per-run noise) to target feature levels.

    Higher severity => more 'PD-like'. All relationships are monotone and noisy.
    """
    s = severity + rng.normal(0, 0.25)  # small run-to-run wobble
    sig = lambda z: 1.0 / (1.0 + np.exp(-z))
    return {
        "blink_rate_per_min": max(2.0, 18.0 - 4.0 * s + rng.normal(0, 1.5)),
        "blink_interval_cv": float(np.clip(0.55 + 0.10 * s + rng.normal(0, 0.05), 0.1, 1.5)),
        "antisacc_error_rate": float(np.clip(sig(-0.9 + 0.85 * s + rng.normal(0, 0.3)), 0.01, 0.95)),
        "antisacc_latency_ms": 290.0 + 35.0 * s + rng.normal(0, 18),
        "antisacc_correction_rate": float(np.clip(0.7 - 0.12 * s + rng.normal(0, 0.08), 0.05, 0.98)),
        "prosacc_error_rate": float(np.clip(sig(-3.0 + 0.5 * s + rng.normal(0, 0.3)), 0.0, 0.4)),
        "prosacc_latency_ms": 210.0 + 24.0 * s + rng.normal(0, 14),
        "pursuit_gain": float(np.clip(0.92 - 0.12 * s + rng.normal(0, 0.04), 0.25, 1.05)),
        "pursuit_catchup_rate": max(0.0, 1.0 + 1.0 * s + rng.normal(0, 0.4)),
        "pursuit_on_target_ratio": float(np.clip(0.82 - 0.09 * s + rng.normal(0, 0.04), 0.05, 0.99)),
        "fixation_dispersion_px": max(1.0, 6.0 + 2.2 * s + rng.normal(0, 1.2)),
    }


# ---------------------------------------------------------------------------
# File writers (tracker-format)
# ---------------------------------------------------------------------------

def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_rest_session(out: Path, sid: str, t: dict, cfg: CohortConfig,
                        rng: np.random.Generator) -> None:
    """Free-viewing/rest session -> frames.csv, blinks.csv, fixations.csv."""
    dur = cfg.rest_duration_sec
    dur_min = dur / 60.0

    # --- blinks: place onsets via gamma-distributed inter-blink intervals with
    #     the target mean rate and CV, then derive blink_detected for frames.
    mean_interval = 60.0 / max(t["blink_rate_per_min"], 1e-6)
    cv = t["blink_interval_cv"]
    shape = 1.0 / (cv ** 2)
    scale = mean_interval / shape
    onsets, clock = [], float(rng.uniform(0, mean_interval))
    while clock < dur:
        onsets.append(clock)
        clock += float(rng.gamma(shape, scale))
    blink_rows = []
    for onset in onsets:
        d_ms = float(np.clip(rng.normal(120, 25), 60, 400))
        blink_rows.append({
            "session_id": sid, "event_id": f"b{len(blink_rows):04d}",
            "start_timestamp_sec": round(onset, 4),
            "end_timestamp_sec": round(onset + d_ms / 1000.0, 4),
            "duration_ms": round(d_ms, 2), "affected_eye": "both", "confidence": 0.9,
        })
    _write_csv(out / f"{sid}_blinks.csv", BLINK_FIELDS, blink_rows)

    # --- frames: minimal but real-format; blink_detected flags the blink windows
    n_frames = int(dur * cfg.fps)
    blink_windows = [(r["start_timestamp_sec"], r["end_timestamp_sec"]) for r in blink_rows]
    frame_rows = []
    for i in range(n_frames):
        ts = i / cfg.fps
        in_blink = any(a <= ts <= b for a, b in blink_windows)
        frame_rows.append({
            "session_id": sid, "frame_number": i, "timestamp_sec": round(ts, 4),
            "blink_detected": int(in_blink),
            "left_ear": 0.12 if in_blink else 0.30, "right_ear": 0.12 if in_blink else 0.30,
            "gaze_x": round(0.5 + rng.normal(0, 0.02), 4),
            "gaze_y": round(0.5 + rng.normal(0, 0.02), 4),
        })
    _write_csv(out / f"{sid}_frames.csv", FRAME_FIELDS, frame_rows)

    # --- fixations: dispersion centred on the target level
    fix_rows = []
    for k in range(cfg.fixations_per_rest):
        disp = max(0.5, rng.normal(t["fixation_dispersion_px"], 1.5))
        start = k * (dur / cfg.fixations_per_rest)
        fix_rows.append({
            "session_id": sid, "event_id": f"f{k:04d}",
            "start_timestamp_sec": round(start, 4),
            "end_timestamp_sec": round(start + 0.3, 4),
            "duration_ms": 300.0, "center_x": 0.5, "center_y": 0.5,
            "dispersion_px": round(disp, 2), "num_frames": 9, "confidence": 0.9,
        })
    _write_csv(out / f"{sid}_fixations.csv", FIXATION_FIELDS, fix_rows)


def _saccade_task_rows(sid: str, task_id: str, n_trials: int, t: dict,
                       is_anti: bool, rng: np.random.Generator) -> list[dict]:
    rows = []
    err_rate = t["antisacc_error_rate"] if is_anti else t["prosacc_error_rate"]
    lat_mean = t["antisacc_latency_ms"] if is_anti else t["prosacc_latency_ms"]
    corr_rate = t["antisacc_correction_rate"]
    for i in range(n_trials):
        tgt_dir = "left" if rng.random() < 0.5 else "right"
        correct_dir = ("right" if tgt_dir == "left" else "left") if is_anti else tgt_dir
        error = rng.random() < err_rate
        corrected = bool(error and rng.random() < corr_rate)
        # An antisaccade error = reflexive look toward target (faster).
        if error and not corrected:
            resp_dir = tgt_dir if is_anti else ("right" if tgt_dir == "left" else "left")
            direction_correct = False
            latency = lat_mean - 60 + rng.normal(0, 20)
        else:
            resp_dir = correct_dir
            direction_correct = True
            latency = lat_mean + rng.normal(0, 22)
        latency = float(max(80.0, latency))
        rows.append({
            "session_id": sid, "task_id": task_id, "trial_id": f"t{i:03d}",
            "trial_number": i, "condition": "none",
            "fixation_onset_sec": round(i * 2.0, 4),
            "target_onset_sec": round(i * 2.0 + 1.0, 4),
            "trial_end_sec": round(i * 2.0 + 2.0, 4),
            "response_detected": 1,
            "response_onset_sec": round(i * 2.0 + 1.0 + latency / 1000.0, 4),
            "response_latency_ms": round(latency, 2),
            "response_direction": resp_dir,
            "response_velocity_px_per_sec": round(float(max(50.0, rng.normal(300, 60))), 2),
            "response_amplitude_px": round(float(max(10.0, rng.normal(120, 25))), 2),
            "target_x": 0.2 if tgt_dir == "left" else 0.8, "target_y": 0.5,
            "target_direction": tgt_dir,
            "direction_correct": int(direction_correct),
            "error_saccade_detected": int(error),
            "correction_made": int(corrected),
        })
    return rows


def _pursuit_task_rows(sid: str, task_id: str, n_cycles: int, t: dict,
                       rng: np.random.Generator) -> list[dict]:
    rows = []
    for c in range(n_cycles):
        gain = float(np.clip(rng.normal(t["pursuit_gain"], 0.05), 0.1, 1.2))
        catchup = int(max(0, round(rng.poisson(max(0.05, t["pursuit_catchup_rate"])))))
        on_target = float(np.clip(rng.normal(t["pursuit_on_target_ratio"], 0.05), 0.0, 1.0))
        rows.append({
            "session_id": sid, "task_id": task_id, "trial_id": f"c{c:03d}",
            "trial_number": c, "cycle_number": c,
            "target_onset_sec": round(c * 4.0, 4), "trial_end_sec": round(c * 4.0 + 4.0, 4),
            "target_peak_velocity_px_per_sec": 240.0,
            "mean_pursuit_gain": round(gain, 3),
            "mean_position_error_px": round(float(max(1.0, rng.normal(20 + 30 * (1 - gain), 5))), 2),
            "time_on_target_ratio": round(on_target, 3),
            "catch_up_saccade_count": catchup,
        })
    return rows


def _write_task_metadata(out: Path, sid: str, task_type: str, subject_id: str) -> None:
    doc = {
        "session_id": sid, "task_id": f"{sid}_task", "task_type": task_type,
        "subject_id": subject_id, "software_version": "synthetic-0.1",
        "timestamp_start": 0.0, "timestamp_end": 0.0,
        "analysis": {}, "disclaimer": _DISCLAIMER,
    }
    with open(out / f"{sid}_task_metadata.json", "w") as fh:
        json.dump(doc, fh, indent=2)


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

def simulate_cohort(out_dir: str | Path, cfg: CohortConfig | None = None) -> Path:
    """Generate a full synthetic cohort. Returns the manifest CSV path."""
    cfg = cfg or CohortConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg.seed)

    subjects = (
        [("control", i) for i in range(cfg.n_control)]
        + [("pd", i) for i in range(cfg.n_pd)]
    )
    manifest_rows: list[dict] = []
    bid = 0
    for group, idx in subjects:
        label = 0 if group == "control" else 1
        subject_id = f"{group[:1].upper()}{idx:03d}"  # e.g. C000, P012
        severity = float(rng.normal(0.0 if label == 0 else cfg.pd_severity_mean, 1.0))
        age = int(np.clip(rng.normal(60, 10), 35, 85))     # matched across groups
        sex = "F" if rng.random() < 0.5 else "M"

        for run in range(cfg.runs_per_subject):
            t = _targets_for_run(severity, rng)
            base = f"{subject_id}_r{run}"
            anti, pro, pur, rest = f"{base}_anti", f"{base}_pro", f"{base}_pur", f"{base}_rest"

            _write_csv(out / f"{anti}_trials.csv", SACCADE_TRIAL_FIELDS,
                       _saccade_task_rows(anti, f"{anti}_task", cfg.antisaccade_trials, t, True, rng))
            _write_task_metadata(out, anti, "antisaccade", subject_id)

            _write_csv(out / f"{pro}_trials.csv", SACCADE_TRIAL_FIELDS,
                       _saccade_task_rows(pro, f"{pro}_task", cfg.prosaccade_trials, t, False, rng))
            _write_task_metadata(out, pro, "prosaccade", subject_id)

            _write_csv(out / f"{pur}_trials.csv", PURSUIT_TRIAL_FIELDS,
                       _pursuit_task_rows(pur, f"{pur}_task", cfg.pursuit_cycles, t, rng))
            _write_task_metadata(out, pur, "smooth_pursuit", subject_id)

            _write_rest_session(out, rest, t, cfg, rng)

            manifest_rows.append({
                "battery_id": f"B{bid:05d}", "subject_id": subject_id, "label": label,
                "age": age, "sex": sex, "run": run,
                "antisacc_sid": anti, "prosacc_sid": pro,
                "pursuit_sid": pur, "rest_sid": rest,
            })
            bid += 1

    manifest_path = out / "manifest.csv"
    _write_csv(manifest_path, MANIFEST_FIELDS, manifest_rows)
    return manifest_path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a synthetic eye-tracking cohort.")
    p.add_argument("--out", default="ml/_synthetic", help="output directory")
    p.add_argument("--n-control", type=int, default=25)
    p.add_argument("--n-pd", type=int, default=25)
    p.add_argument("--runs", type=int, default=2, help="runs (visits) per subject")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--pd-severity", type=float, default=1.3,
                   help="mean latent severity of the PD group (higher = easier task)")
    a = p.parse_args()
    cfg = CohortConfig(n_control=a.n_control, n_pd=a.n_pd, runs_per_subject=a.runs,
                       seed=a.seed, pd_severity_mean=a.pd_severity)
    path = simulate_cohort(a.out, cfg)
    n_subj = a.n_control + a.n_pd
    print(f"Wrote synthetic cohort: {n_subj} subjects x {a.runs} runs "
          f"= {n_subj * a.runs} batteries")
    print(f"Manifest: {path}")
    print("\n" + _DISCLAIMER)


if __name__ == "__main__":
    main()
