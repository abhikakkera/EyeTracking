"""
Assemble a modelling table from a data directory + manifest.

One row per "battery" (one assessment of one subject). The label and subject_id
travel together from the manifest — labels are NEVER read from raw tracker output.
``subject_id`` is returned separately as the CV grouping key.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.features import extract_battery_features
from ml.schema import FEATURE_COLUMNS


def build_dataset(data_dir: str | Path, manifest_path: str | Path | None = None) -> pd.DataFrame:
    """Return a DataFrame with meta columns + one column per feature.

    Columns: battery_id, subject_id, label, age, sex, run, <FEATURE_COLUMNS...>
    """
    data_dir = Path(data_dir)
    manifest_path = Path(manifest_path) if manifest_path else data_dir / "manifest.csv"
    manifest = pd.read_csv(manifest_path)

    rows = []
    for _, m in manifest.iterrows():
        feats = extract_battery_features(m.to_dict(), data_dir)
        rows.append({
            "battery_id": m["battery_id"], "subject_id": m["subject_id"],
            "label": int(m["label"]), "age": m.get("age"), "sex": m.get("sex"),
            "run": m.get("run"), **feats,
        })
    df = pd.DataFrame(rows)
    # Stable column order.
    return df[["battery_id", "subject_id", "label", "age", "sex", "run", *FEATURE_COLUMNS]]


def get_Xy_groups(df: pd.DataFrame):
    """Split the table into (X, y, groups) for scikit-learn.

    groups = subject_id, so GroupKFold keeps every subject entirely on one side
    of each split. X is left as a DataFrame so a Pipeline imputer handles NaNs.
    """
    X = df[FEATURE_COLUMNS].copy()
    y = df["label"].to_numpy()
    groups = df["subject_id"].to_numpy()
    return X, y, groups
