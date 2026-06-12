"""Output layout for the PCA Intelligence component.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/pca/runs/<run_id>/`` directory and never overwrites an
earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/pca/runs/<run_id>/
    ├── models/<profile>/
    │   ├── scaler.joblib              fitted per-profile scaler
    │   ├── pca.joblib                 fitted per-profile PCA model
    │   └── model_meta.json            features, k, EVR, medians, lib versions
    ├── scores/<profile>/
    │   ├── scores.parquet             pc_*, t2, q_spe, recon_error, is_train
    │   └── contributions.parquet      per-feature squared residual (sums to q_spe)
    ├── loadings.parquet               long-form (profile, component, feature, loading)
    ├── explained_variance.parquet     (profile, component, evr, cumulative_evr)
    ├── skipped_profiles.parquet       (profile, reason, n_train, n_features)
    ├── pca_intelligence_report.{json,md}   ``Finding`` report
    └── pca_fit_manifest.json          written LAST — marks the run complete
"""

from __future__ import annotations

from pathlib import Path

from src.config import INTELLIGENCE_DIR

PCA_DIR = INTELLIGENCE_DIR / "pca"

MANIFEST_NAME = "pca_fit_manifest.json"
LOADINGS_FILE = "loadings.parquet"
EXPLAINED_VARIANCE_FILE = "explained_variance.parquet"
SKIPPED_FILE = "skipped_profiles.parquet"
REPORT_JSON = "pca_intelligence_report.json"
REPORT_MD = "pca_intelligence_report.md"

SCALER_FILE = "scaler.joblib"
PCA_FILE = "pca.joblib"
MODEL_META_FILE = "model_meta.json"
SCORES_FILE = "scores.parquet"
CONTRIBUTIONS_FILE = "contributions.parquet"


def model_dir(out: Path, profile: str) -> Path:
    """Per-profile model directory inside a run."""
    return out / "models" / profile


def scores_dir(out: Path, profile: str) -> Path:
    """Per-profile scores directory inside a run."""
    return out / "scores" / profile
