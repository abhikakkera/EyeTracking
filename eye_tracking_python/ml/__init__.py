"""
PDEYE ML — Parkinson's-screening research pipeline (PROTOTYPE).

⚠️ RESEARCH PROTOTYPE — NOT A MEDICAL DEVICE.
This package trains and evaluates machine-learning models on eye-movement
features for *research purposes only*. It does NOT diagnose, treat, predict,
or screen for Parkinson's disease or any other condition. A screening aid is
not a diagnosis. Any clinical use would require labelled clinical data, ethics
(IRB) approval, prospective validation, and regulatory review.

The pipeline reads the *exact files the tracker already exports*
(``sessions/<id>_*.csv`` and ``<id>_trials.csv``), so the same feature code
runs unchanged on synthetic data today and on real subject data later.
"""

__version__ = "0.1.0"
