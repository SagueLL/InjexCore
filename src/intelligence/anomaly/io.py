"""Output layout for the Anomaly Intelligence component.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/anomaly/runs/<run_id>/`` directory and never overwrites
an earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/anomaly/runs/<run_id>/
    ├── models/<profile>/
    │   ├── isolation_forest.joblib    fitted, seeded Isolation Forest
    │   ├── mahalanobis.json           mean + precision matrix (transparent JSON)
    │   └── model_meta.json            features, medians, lib versions
    ├── scores/
    │   └── anomaly_scores.parquet     full scored dataset (spec schema)
    ├── combine_calibration.parquet    per-(profile, detector) train ECDF grid
    ├── summaries/
    │   ├── timeline.parquet           severity counts per time bucket
    │   ├── rates_by_profile.parquet   anomaly/warning rates per profile
    │   ├── severity_distribution.parquet
    │   ├── top_events.parquet         highest combined scores + evidence
    │   └── detector_agreement.parquet pairwise co-trigger counts per profile
    ├── unsupported_profiles.parquet   (profile, detector, reason)
    ├── anomaly_intelligence_report.{json,md}   ``Finding`` report
    └── anomaly_fit_manifest.json      written LAST — marks the run complete
"""

from __future__ import annotations

from pathlib import Path

from src.config import INTELLIGENCE_DIR

ANOMALY_DIR = INTELLIGENCE_DIR / "anomaly"

MANIFEST_NAME = "anomaly_fit_manifest.json"
SCORES_FILE = Path("scores") / "anomaly_scores.parquet"
CALIBRATION_FILE = "combine_calibration.parquet"
UNSUPPORTED_FILE = "unsupported_profiles.parquet"
REPORT_JSON = "anomaly_intelligence_report.json"
REPORT_MD = "anomaly_intelligence_report.md"

TIMELINE_FILE = Path("summaries") / "timeline.parquet"
RATES_FILE = Path("summaries") / "rates_by_profile.parquet"
SEVERITY_FILE = Path("summaries") / "severity_distribution.parquet"
TOP_EVENTS_FILE = Path("summaries") / "top_events.parquet"
AGREEMENT_FILE = Path("summaries") / "detector_agreement.parquet"

IFOREST_FILE = "isolation_forest.joblib"
MAHALANOBIS_FILE = "mahalanobis.json"
MODEL_META_FILE = "model_meta.json"


def model_dir(out: Path, profile: str) -> Path:
    """Per-profile model directory inside a run."""
    return out / "models" / profile
