"""
Score ONE assessment ("battery") with a trained model.

⚠️ READ THIS. The number produced here is a **research pattern-similarity
score**, not a diagnosis and not a probability of having Parkinson's disease:

  * It only says how similar one person's eye-movement features are to the
    model's "PD" training group.
  * On synthetic data it is meaningless about real disease.
  * Even on real data, a model score is NOT a "chance of disease" unless it has
    been calibrated to the real-world base rate. A screening aid flags "maybe
    worth a closer look" — it never decides.

Use ``score_battery`` for one person; ``ml.train`` already saves honest
out-of-fold scores for everyone in a cohort (``predictions.csv``).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.features import extract_battery_features
from ml.schema import FEATURE_COLUMNS

# Bands for the 0-100 pattern score. Deliberately vague language — NOT verdicts.
_BANDS = [
    (0.34, "LOW similarity to the PD-pattern group"),
    (0.67, "MEDIUM similarity to the PD-pattern group"),
    (1.01, "HIGH similarity to the PD-pattern group"),
]

_DISCLAIMER = (
    "Research pattern score — NOT a diagnosis, NOT a probability of disease. "
    "A screening aid flags 'maybe look closer'; it never decides. This prototype "
    "is trained on synthetic data and has no clinical validation."
)


def pattern_band(score: float) -> str:
    """Map a 0..1 score to a vague similarity band (never a verdict)."""
    for hi, label in _BANDS:
        if score < hi:
            return label
    return _BANDS[-1][1]


def score_battery(model, manifest_row: dict, data_dir: str | Path) -> dict:
    """Return the model's pattern score for one battery.

    ``model`` is a fitted sklearn pipeline (e.g. loaded from model.joblib).
    ``manifest_row`` has the session ids (see schema.MANIFEST_FIELDS).
    """
    feats = extract_battery_features(manifest_row, data_dir)
    X = pd.DataFrame([feats])[FEATURE_COLUMNS]
    prob = float(model.predict_proba(X)[0, 1])
    return {
        "pd_pattern_score": prob,
        "score_0_100": round(prob * 100, 1),
        "band": pattern_band(prob),
        "features": feats,
        "disclaimer": _DISCLAIMER,
    }


def _load_model(artifacts_dir: Path):
    import joblib
    path = artifacts_dir / "model.joblib"
    if not path.exists():
        raise FileNotFoundError(
            f"No model at {path}. Run `python -m ml.train` first.")
    return joblib.load(path)


def main() -> None:
    p = argparse.ArgumentParser(description="Score one assessment (research only).")
    p.add_argument("--data-dir", default="ml/_synthetic")
    p.add_argument("--artifacts", default="ml/_artifacts")
    p.add_argument("--battery", help="battery_id from manifest.csv (default: first row)")
    p.add_argument("--manifest", default=None)
    a = p.parse_args()

    data_dir = Path(a.data_dir)
    manifest = pd.read_csv(a.manifest or data_dir / "manifest.csv")
    row = (manifest[manifest["battery_id"] == a.battery].iloc[0] if a.battery
           else manifest.iloc[0]).to_dict()

    model = _load_model(Path(a.artifacts))
    res = score_battery(model, row, data_dir)

    print("\n" + "=" * 56)
    print(f"  Battery {row['battery_id']}  (subject {row['subject_id']})")
    print("=" * 56)
    print(f"  PD-pattern score : {res['score_0_100']:.1f} / 100")
    print(f"  Interpretation   : {res['band']}")
    print("-" * 56)
    print("  " + _DISCLAIMER)
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
