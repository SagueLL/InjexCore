"""Output layout + upstream-run loading for the Controlled Scoring Experiment.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/scoring_experiments/runs/<run_id>/`` directory and never
overwrites an earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/scoring_experiments/runs/<run_id>/
    ├── scenario_definitions.parquet
    ├── scenario_scores.parquet                 per-row review view (non-normal rows)
    ├── scenario_incident_comparison.parquet
    ├── scenario_anomaly_rate_comparison.parquet
    ├── scenario_drift_comparison.parquet
    ├── scenario_recommendations.parquet
    ├── controlled_scoring_report.md
    ├── controlled_scoring_findings.json
    └── controlled_scoring_manifest.json        written LAST — marks completion

The decision-report addendum (when enabled) lands under
``data/intelligence/forensics/reference_decision/<run_id>/`` — read-only over
every upstream artifact. All upstream loading is strictly read-only: persisted
runs are consumed as files, never re-fitted, never modified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import INTELLIGENCE_DIR, PROJECT_ROOT
from src.intelligence._common.fingerprint import file_sha256
from src.intelligence._common.io import write_manifest, write_table
from src.intelligence._common.runs import (
    LATEST,
    create_run_dir,
    new_run_id,
    resolve_run,
    run_dir,
)
from src.intelligence.drift.io import (
    load_anomaly_scores,
    load_operational_timeline,
)

__all__ = [
    "SCORING_DIR",
    "DECISION_DIR",
    "MANIFEST_NAME",
    "DECISION_MANIFEST_NAME",
    "SCENARIO_DEFINITIONS_FILE",
    "SCENARIO_SCORES_FILE",
    "INCIDENT_COMPARISON_FILE",
    "ANOMALY_RATE_COMPARISON_FILE",
    "DRIFT_COMPARISON_FILE",
    "RECOMMENDATIONS_FILE",
    "REPORT_MD",
    "FINDINGS_JSON",
    "ANOMALY_MANIFEST",
    "SENSOR_HEALTH_MANIFEST",
    "DRIFT_MANIFEST",
    "INCIDENTS_MANIFEST",
    "OPERATIONAL_MANIFEST",
    "REFERENCE_MANIFEST",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "create_run_dir",
    "write_manifest",
    "write_table",
    "file_sha256",
    "load_anomaly_scores",
    "load_operational_timeline",
    "resolve_project_path",
    "load_run_manifest",
    "load_raw_vs_healthy",
    "load_incidents",
    "load_suppressed_duplicates",
    "load_recommended_actions",
    "load_reference_quarantine",
    "load_reference_proposals",
]

SCORING_DIR = INTELLIGENCE_DIR / "scoring_experiments"
DECISION_DIR = INTELLIGENCE_DIR / "forensics" / "reference_decision"

MANIFEST_NAME = "controlled_scoring_manifest.json"
DECISION_MANIFEST_NAME = "reference_decision_manifest.json"
SCENARIO_DEFINITIONS_FILE = "scenario_definitions.parquet"
SCENARIO_SCORES_FILE = "scenario_scores.parquet"
INCIDENT_COMPARISON_FILE = "scenario_incident_comparison.parquet"
ANOMALY_RATE_COMPARISON_FILE = "scenario_anomaly_rate_comparison.parquet"
DRIFT_COMPARISON_FILE = "scenario_drift_comparison.parquet"
RECOMMENDATIONS_FILE = "scenario_recommendations.parquet"
REPORT_MD = "controlled_scoring_report.md"
FINDINGS_JSON = "controlled_scoring_findings.json"

# Upstream run-internal contracts (read-only).
ANOMALY_MANIFEST = "anomaly_fit_manifest.json"
SENSOR_HEALTH_MANIFEST = "sensor_health_manifest.json"
DRIFT_MANIFEST = "drift_manifest.json"
INCIDENTS_MANIFEST = "incidents_manifest.json"
OPERATIONAL_MANIFEST = "operational_context_manifest.json"
REFERENCE_MANIFEST = "reference_governance_manifest.json"
REFERENCE_QUARANTINE_FILE = "quarantine_proposals.parquet"
REFERENCE_PROPOSALS_FILE = "reference_proposals.parquet"


def resolve_project_path(path_str: str) -> Path:
    """Resolve a policy path string against the project root."""
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_run_manifest(run_dir_path: Path, manifest_name: str) -> dict[str, Any]:
    """Load a completed upstream run's manifest."""
    path = run_dir_path / manifest_name
    if not path.exists():
        raise FileNotFoundError(f"Upstream manifest not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_timestamps(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_raw_vs_healthy(drift_run: Path) -> pd.DataFrame:
    """Drift raw-vs-healthy-only comparison (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(
            drift_run / "summaries" / "raw_vs_healthy_only_comparison.parquet"
        ),
        ("window_start",),
    )


def load_incidents(incidents_run: Path) -> pd.DataFrame:
    """Aggregated incidents (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(incidents_run / "incidents" / "incidents.parquet"),
        ("start_timestamp", "end_timestamp"),
    )


def load_suppressed_duplicates(incidents_run: Path) -> pd.DataFrame:
    """Suppressed duplicate incidents (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(
            incidents_run / "incidents" / "suppressed_duplicate_events.parquet"
        ),
        ("start_timestamp", "end_timestamp"),
    )


def load_recommended_actions(incidents_run: Path) -> pd.DataFrame:
    """Per-incident recommended actions (read-only)."""
    return pd.read_parquet(incidents_run / "incidents" / "recommended_actions.parquet")


def load_reference_quarantine(reference_run: Path) -> pd.DataFrame:
    """Quarantine proposals from a completed reference governance run."""
    return _parse_timestamps(
        pd.read_parquet(reference_run / REFERENCE_QUARANTINE_FILE),
        ("start_timestamp", "end_timestamp"),
    )


def load_reference_proposals(reference_run: Path) -> pd.DataFrame:
    """Candidate reference proposals from a completed reference run."""
    return pd.read_parquet(reference_run / REFERENCE_PROPOSALS_FILE)
