"""
Baseline training + honest evaluation.

Model: median-impute -> standardize -> RandomForest (or GradientBoosting).
The imputer/scaler live INSIDE the pipeline, so they are re-fit on the training
portion of every CV fold — no information leaks from validation rows.

Evaluation is done with SUBJECT-LEVEL cross-validation (StratifiedGroupKFold):
every subject is entirely in train OR test for a given fold, never both.

``--demo-leakage`` ALSO runs naive row-level CV (ignoring subject) and prints the
inflated score next to the honest one, to show exactly how much subject leakage
flatters the numbers.

⚠️ Screening aid, not a diagnosis. On synthetic data this only proves the
pipeline recovers a signal that was injected on purpose.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.dataset import build_dataset, get_Xy_groups
from ml.schema import FEATURE_COLUMNS

_DISCLAIMER = (
    "RESEARCH PROTOTYPE — screening aid, NOT a diagnosis and NOT a medical device. "
    "Results on synthetic data only show the pipeline works; they say nothing about "
    "real Parkinson's disease."
)


def make_model(kind: str, seed: int) -> Pipeline:
    if kind == "rf":
        clf = RandomForestClassifier(
            n_estimators=400, max_depth=None, min_samples_leaf=2,
            class_weight="balanced", random_state=seed, n_jobs=-1,
        )
    elif kind == "gb":
        clf = GradientBoostingClassifier(random_state=seed)
    else:
        raise ValueError(f"unknown model kind: {kind}")
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", clf),
    ])


def _metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    sens = tp / (tp + fn) if (tp + fn) else float("nan")   # recall for PD class
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    return {
        "auroc": float(roc_auc_score(y_true, y_prob)),
        "average_precision": float(average_precision_score(y_true, y_prob)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "sensitivity": float(sens),
        "specificity": float(spec),
        "threshold": threshold,
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def _oof_predict(model_kind, X, y, groups, cv, seed) -> np.ndarray:
    """Out-of-fold predicted probabilities for the positive (PD) class."""
    oof = np.full(len(y), np.nan)
    for train_idx, test_idx in cv.split(X, y, groups):
        model = make_model(model_kind, seed)
        model.fit(X.iloc[train_idx], y[train_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    return oof


def _youden_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    fpr, tpr, thr = roc_curve(y_true, y_prob)
    j = tpr - fpr
    return float(thr[int(np.argmax(j))])


def _univariate_separation(X: pd.DataFrame, y: np.ndarray) -> list[dict]:
    """How well each single feature separates the groups (descriptive).

    Reported as AUROC of the lone feature vs. label, with the PD direction. This
    is more interpretable than permutation importance when features are
    correlated (which dilutes permutation importance across the correlated set).
    Descriptive only — not a performance estimate.
    """
    Xi = SimpleImputer(strategy="median").fit_transform(X)
    out = []
    for j, col in enumerate(FEATURE_COLUMNS):
        vals = Xi[:, j]
        if np.unique(vals).size < 2:
            auc, direction = 0.5, "none"
        else:
            raw = roc_auc_score(y, vals)
            auc = max(raw, 1.0 - raw)            # separation strength
            direction = "higher_in_pd" if raw >= 0.5 else "lower_in_pd"
        out.append({"feature": col, "auroc": float(auc), "direction": direction})
    return sorted(out, key=lambda r: r["auroc"], reverse=True)


def run(data_dir, manifest, out_dir, model_kind="rf", folds=5, seed=0,
        demo_leakage=True) -> dict:
    df = build_dataset(data_dir, manifest)
    X, y, groups = get_Xy_groups(df)

    n_subjects = len(np.unique(groups))
    n_pos, n_neg = int(y.sum()), int((y == 0).sum())
    # GroupKFold can't have more folds than the smaller class has subjects.
    subj_label = df.groupby("subject_id")["label"].first()
    max_folds = int(min(subj_label.value_counts()))
    folds = max(2, min(folds, max_folds))

    # ---- honest: subject-level CV ----
    sgkf = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    oof_grouped = _oof_predict(model_kind, X, y, groups, sgkf, seed)
    thr = _youden_threshold(y, oof_grouped)
    grouped = _metrics(y, oof_grouped, threshold=thr)

    report: dict = {
        "n_batteries": int(len(df)),
        "n_subjects": int(n_subjects),
        "class_balance": {"control": n_neg, "pd": n_pos},
        "cv_folds": folds,
        "model": model_kind,
        "subject_level_cv": grouped,
        "disclaimer": _DISCLAIMER,
    }

    # ---- leakage demo: naive row-level CV ----
    if demo_leakage:
        skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        oof_naive = _oof_predict(model_kind, X, y, None, skf, seed)
        naive = _metrics(y, oof_naive, threshold=0.5)
        report["naive_rowlevel_cv"] = naive
        report["leakage_auroc_inflation"] = round(naive["auroc"] - grouped["auroc"], 4)

    # ---- which features separate the groups (descriptive) ----
    report["univariate_separation"] = _univariate_separation(X, y)

    # Final model fit on all data (saved for reuse / inspection).
    final = make_model(model_kind, seed).fit(X, y)

    # ---- save artifacts ----
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "features.csv", index=False)
    with open(out / "report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    try:
        import joblib
        joblib.dump(final, out / "model.joblib")
    except Exception:  # joblib optional
        pass

    _print_report(report)
    return report


def _print_report(r: dict) -> None:
    g = r["subject_level_cv"]
    print("\n" + "=" * 64)
    print("  PDEYE ML — baseline evaluation (SYNTHETIC DATA)")
    print("=" * 64)
    print(f"  subjects: {r['n_subjects']}   batteries: {r['n_batteries']}   "
          f"control/pd: {r['class_balance']['control']}/{r['class_balance']['pd']}")
    print(f"  model: {r['model']}   subject-level folds: {r['cv_folds']}")
    print("-" * 64)
    print("  SUBJECT-LEVEL CV (the number you should trust):")
    print(f"    AUROC               {g['auroc']:.3f}")
    print(f"    Avg precision       {g['average_precision']:.3f}")
    print(f"    Balanced accuracy   {g['balanced_accuracy']:.3f}")
    print(f"    Sensitivity         {g['sensitivity']:.3f}   "
          f"Specificity {g['specificity']:.3f}  (thr={g['threshold']:.2f})")
    if "naive_rowlevel_cv" in r:
        n = r["naive_rowlevel_cv"]
        print("-" * 64)
        print("  NAIVE ROW-LEVEL CV (WRONG — leaks subject identity):")
        print(f"    AUROC               {n['auroc']:.3f}")
        print(f"    >>> leakage inflated AUROC by "
              f"{r['leakage_auroc_inflation']:+.3f} <<<")
    print("-" * 64)
    print("  Top features (univariate separation, AUROC vs label):")
    for row in r["univariate_separation"][:5]:
        print(f"    {row['feature']:<28} {row['auroc']:.3f}  ({row['direction']})")
    print("=" * 64)
    print("  " + _DISCLAIMER)
    print("=" * 64 + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Train + evaluate the PD-screening baseline.")
    p.add_argument("--data-dir", default="ml/_synthetic")
    p.add_argument("--manifest", default=None, help="defaults to <data-dir>/manifest.csv")
    p.add_argument("--out", default="ml/_artifacts")
    p.add_argument("--model", choices=["rf", "gb"], default="rf")
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-leakage-demo", action="store_true")
    a = p.parse_args()
    run(a.data_dir, a.manifest, a.out, model_kind=a.model, folds=a.folds,
        seed=a.seed, demo_leakage=not a.no_leakage_demo)


if __name__ == "__main__":
    main()
