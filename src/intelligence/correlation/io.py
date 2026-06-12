"""Output layout for the Correlation Intelligence component.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/correlation/runs/<run_id>/`` directory and never
overwrites an earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/correlation/runs/<run_id>/
    ├── correlations.parquet           long-form per-(profile, pair) Pearson/Spearman/n_valid
    ├── excluded_features.parquet      per-(profile, feature) exclusion reasons
    ├── strong_pairs.parquet           |pearson| >= strong_threshold
    ├── redundant_pairs.parquet        both metrics >= redundancy_threshold
    ├── correlation_shift.parquet      train-vs-validation deltas (diagnostics)
    ├── correlation_intelligence_report.{json,md}   ``Finding`` report
    └── correlation_fit_manifest.json  written LAST — marks the run complete
"""

from __future__ import annotations

from src.config import INTELLIGENCE_DIR

CORRELATION_DIR = INTELLIGENCE_DIR / "correlation"

MANIFEST_NAME = "correlation_fit_manifest.json"
CORRELATIONS_FILE = "correlations.parquet"
EXCLUDED_FILE = "excluded_features.parquet"
STRONG_FILE = "strong_pairs.parquet"
REDUNDANT_FILE = "redundant_pairs.parquet"
SHIFT_FILE = "correlation_shift.parquet"
REPORT_JSON = "correlation_intelligence_report.json"
REPORT_MD = "correlation_intelligence_report.md"
