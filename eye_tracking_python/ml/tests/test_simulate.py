"""The simulator writes real-format files and injects the intended effects."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.dataset import build_dataset
from ml.schema import MANIFEST_FIELDS
from ml.simulate import CohortConfig, simulate_cohort


def _small_cfg(**kw) -> CohortConfig:
    base = dict(n_control=8, n_pd=8, runs_per_subject=2, rest_duration_sec=20.0,
                pursuit_cycles=4, seed=0)
    base.update(kw)
    return CohortConfig(**base)


def test_manifest_and_files_written(tmp_path: Path):
    manifest_path = simulate_cohort(tmp_path, _small_cfg())
    assert manifest_path.exists()
    m = pd.read_csv(manifest_path)
    assert list(m.columns) == MANIFEST_FIELDS
    assert len(m) == 16 * 2  # 16 subjects x 2 runs

    # Every referenced session file actually exists.
    row = m.iloc[0]
    for sid_col in ["antisacc_sid", "prosacc_sid", "pursuit_sid"]:
        assert (tmp_path / f"{row[sid_col]}_trials.csv").exists()
        assert (tmp_path / f"{row[sid_col]}_task_metadata.json").exists()
    assert (tmp_path / f"{row['rest_sid']}_blinks.csv").exists()
    assert (tmp_path / f"{row['rest_sid']}_frames.csv").exists()
    assert (tmp_path / f"{row['rest_sid']}_fixations.csv").exists()


def test_injected_effect_direction(tmp_path: Path):
    """PD group should show the injected direction on key features (group means)."""
    simulate_cohort(tmp_path, _small_cfg(pd_severity_mean=1.5))
    df = build_dataset(tmp_path)
    ctrl = df[df.label == 0]
    pd_ = df[df.label == 1]
    # Blink rate lower in PD; antisaccade error rate higher; pursuit gain lower.
    assert ctrl["blink_rate_per_min"].mean() > pd_["blink_rate_per_min"].mean()
    assert ctrl["antisacc_error_rate"].mean() < pd_["antisacc_error_rate"].mean()
    assert ctrl["pursuit_gain_mean"].mean() > pd_["pursuit_gain_mean"].mean()


def test_reproducible_with_seed(tmp_path: Path):
    a = simulate_cohort(tmp_path / "a", _small_cfg(seed=42))
    b = simulate_cohort(tmp_path / "b", _small_cfg(seed=42))
    assert pd.read_csv(a).equals(pd.read_csv(b))
