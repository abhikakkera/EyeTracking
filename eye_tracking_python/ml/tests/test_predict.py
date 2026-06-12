"""Per-person scoring produces a valid score and honest bands."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.predict import pattern_band, score_battery
from ml.simulate import CohortConfig, simulate_cohort
from ml.train import make_model
from ml.dataset import build_dataset, get_Xy_groups


def test_pattern_band_thresholds():
    assert "LOW" in pattern_band(0.10)
    assert "MEDIUM" in pattern_band(0.50)
    assert "HIGH" in pattern_band(0.90)


def test_score_battery_in_range(tmp_path: Path):
    simulate_cohort(tmp_path, CohortConfig(n_control=6, n_pd=6, runs_per_subject=2,
                                           rest_duration_sec=15.0, pursuit_cycles=3, seed=0))
    # Train a model on the cohort.
    df = build_dataset(tmp_path)
    X, y, _ = get_Xy_groups(df)
    model = make_model("rf", 0).fit(X, y)

    manifest = pd.read_csv(tmp_path / "manifest.csv")
    res = score_battery(model, manifest.iloc[0].to_dict(), tmp_path)

    assert 0.0 <= res["pd_pattern_score"] <= 1.0
    assert 0.0 <= res["score_0_100"] <= 100.0
    assert res["band"] in (
        "LOW similarity to the PD-pattern group",
        "MEDIUM similarity to the PD-pattern group",
        "HIGH similarity to the PD-pattern group",
    )
    # Honest framing must travel with the result.
    assert "not a diagnosis" in res["disclaimer"].lower()
