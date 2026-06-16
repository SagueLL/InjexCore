"""Output layout + upstream-run loading for Reference Governance.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/reference/runs/<run_id>/`` directory and never
overwrites an earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/reference/runs/<run_id>/
    ├── reference_registry.parquet            current + candidate references
    ├── reference_proposals.parquet           candidate reference proposals
    ├── quarantine_proposals.parquet          sensor quarantine proposals
    ├── decision_log.parquet                  one pending row per proposal
    ├── reference_governance_report.md
    ├── reference_governance_findings.json
    └── reference_governance_manifest.json    written LAST — marks completion

All upstream loading is strictly read-only: persisted runs are consumed as
files, never re-fitted, never modified.
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
from src.intelligence._common.upstream import load_behaviour_manifest

__all__ = [
    "REFERENCE_DIR",
    "MANIFEST_NAME",
    "REGISTRY_FILE",
    "PROPOSALS_FILE",
    "QUARANTINE_FILE",
    "DECISION_LOG_FILE",
    "REPORT_MD",
    "FINDINGS_JSON",
    "SENSOR_HEALTH_MANIFEST",
    "INCIDENTS_MANIFEST",
    "DRIFT_MANIFEST",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "create_run_dir",
    "write_manifest",
    "write_table",
    "file_sha256",
    "load_behaviour_manifest",
    "resolve_project_path",
    "load_run_manifest",
    "load_quarantine_recommendations",
    "load_sensor_health_events",
    "load_incidents",
    "load_recommended_actions",
    "load_suppressed_duplicates",
    "load_drift_events",
    "load_raw_vs_healthy",
]

REFERENCE_DIR = INTELLIGENCE_DIR / "reference"

MANIFEST_NAME = "reference_governance_manifest.json"
REGISTRY_FILE = "reference_registry.parquet"
PROPOSALS_FILE = "reference_proposals.parquet"
QUARANTINE_FILE = "quarantine_proposals.parquet"
DECISION_LOG_FILE = "decision_log.parquet"
REPORT_MD = "reference_governance_report.md"
FINDINGS_JSON = "reference_governance_findings.json"

# Upstream run-internal contracts (read-only).
SENSOR_HEALTH_MANIFEST = "sensor_health_manifest.json"
INCIDENTS_MANIFEST = "incidents_manifest.json"
DRIFT_MANIFEST = "drift_manifest.json"


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


def load_quarantine_recommendations(sensor_health_run: Path) -> pd.DataFrame:
    """Sensor-health quarantine recommendations (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(
            sensor_health_run / "summaries" / "quarantine_recommendations.parquet"
        ),
        ("start_timestamp", "end_timestamp"),
    )


def load_sensor_health_events(sensor_health_run: Path) -> pd.DataFrame:
    """Sensor-health events (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(sensor_health_run / "events" / "sensor_health_events.parquet"),
        ("start_timestamp", "end_timestamp"),
    )


def load_incidents(incidents_run: Path) -> pd.DataFrame:
    """Aggregated incidents (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(incidents_run / "incidents" / "incidents.parquet"),
        ("start_timestamp", "end_timestamp"),
    )


def load_recommended_actions(incidents_run: Path) -> pd.DataFrame:
    """Per-incident recommended actions (read-only)."""
    return pd.read_parquet(incidents_run / "incidents" / "recommended_actions.parquet")


def load_suppressed_duplicates(incidents_run: Path) -> pd.DataFrame:
    """Suppressed duplicate incidents (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(
            incidents_run / "incidents" / "suppressed_duplicate_events.parquet"
        ),
        ("start_timestamp", "end_timestamp"),
    )


def load_drift_events(drift_run: Path) -> pd.DataFrame:
    """Drift events from a completed drift run (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(drift_run / "events" / "drift_events.parquet"),
        ("start_timestamp", "end_timestamp"),
    )


def load_raw_vs_healthy(drift_run: Path) -> pd.DataFrame:
    """Drift raw-vs-healthy-only comparison (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(
            drift_run / "summaries" / "raw_vs_healthy_only_comparison.parquet"
        ),
        ("window_start",),
    )
