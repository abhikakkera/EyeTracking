"""Simulate -> build dataset -> train. The pipeline must recover the injected
signal under honest subject-level CV, and write its artifacts."""
from __future__ import annotations

from pathlib import Path

from ml.simulate import CohortConfig, simulate_cohort
from ml.train import run


def test_end_to_end_recovers_signal(tmp_path: Path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "artifacts"
    # Well-separated cohort so the assertion is robust, not flaky.
    simulate_cohort(data_dir, CohortConfig(
        n_control=10, n_pd=10, runs_per_subject=2,
        rest_duration_sec=20.0, pursuit_cycles=6, pd_severity_mean=1.7, seed=3))

    report = run(data_dir, None, out_dir, model_kind="rf", folds=3, seed=0,
                 demo_leakage=True)

    # Honest subject-level AUROC should clearly beat chance on injected signal.
    assert report["subject_level_cv"]["auroc"] > 0.6
    # Artifacts written.
    assert (out_dir / "report.json").exists()
    assert (out_dir / "features.csv").exists()
    # Leakage demo present and numeric.
    assert "naive_rowlevel_cv" in report
    assert isinstance(report["leakage_auroc_inflation"], float)
