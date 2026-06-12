"""The anti-leakage guarantee: no subject is ever in train AND test of a fold."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from ml.dataset import build_dataset, get_Xy_groups
from ml.simulate import CohortConfig, simulate_cohort


def _build(tmp_path: Path):
    simulate_cohort(tmp_path, CohortConfig(n_control=8, n_pd=8, runs_per_subject=3,
                                           rest_duration_sec=15.0, pursuit_cycles=3, seed=1))
    return build_dataset(tmp_path)


def test_each_subject_has_single_label(tmp_path: Path):
    df = _build(tmp_path)
    per_subject_labels = df.groupby("subject_id")["label"].nunique()
    assert (per_subject_labels == 1).all(), "a subject must not have two labels"


def test_no_subject_spans_train_and_test(tmp_path: Path):
    df = _build(tmp_path)
    X, y, groups = get_Xy_groups(df)
    # multiple rows per subject is what makes this test meaningful
    assert len(df) > len(np.unique(groups))

    sgkf = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=0)
    for train_idx, test_idx in sgkf.split(X, y, groups):
        train_subjects = set(groups[train_idx])
        test_subjects = set(groups[test_idx])
        assert train_subjects.isdisjoint(test_subjects)
