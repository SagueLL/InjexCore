"""Output layout + upstream-run loading for Incident Aggregation.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/incidents/runs/<run_id>/`` directory and never
overwrites an earlier run::

    data/intelligence/incidents/runs/<run_id>/
    ├── incidents/
    │   ├── incidents.parquet
    │   ├── incident_relationships.parquet
    │   ├── incident_review_pack.parquet
    │   ├── incident_timeline.parquet
    │   ├── incident_summary.parquet
    │   ├── recommended_actions.parquet
    │   ├── suppressed_duplicate_events.parquet
    │   └── unsupported_incident_sources.parquet
    ├── incidents_report.md
    ├── incidents_findings.json
    └── incidents_manifest.json               written LAST — marks completion

The drift-aware forensic addendum (when enabled) lands under
``data/intelligence/forensics/drift_addenda/<run_id>/`` — read-only over
every upstream artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import INTELLIGENCE_DIR, PROJECT_ROOT
from src.intelligence._common.fingerprint import file_sha256
from src.intelligence._common.io import write_manifest, write_table
from src.intelligence._common.runs import LATEST, new_run_id, resolve_run, run_dir
from src.intelligence.drift import io as drift_io

__all__ = [
    "INCIDENTS_DIR",
    "ADDENDA_DIR",
    "MANIFEST_NAME",
    "ADDENDUM_MANIFEST_NAME",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "write_manifest",
    "write_table",
    "file_sha256",
    "resolve_project_path",
    "load_run_manifest",
    "load_drift_artifacts",
    "load_sensor_health_events",
    "load_anomaly_scores",
    "load_operational_artifacts",
    "load_bom_transitions",
]

INCIDENTS_DIR = INTELLIGENCE_DIR / "incidents"
ADDENDA_DIR = INTELLIGENCE_DIR / "forensics" / "drift_addenda"

MANIFEST_NAME = "incidents_manifest.json"
ADDENDUM_MANIFEST_NAME = "drift_addendum_manifest.json"
INCIDENTS_FILE = Path("incidents") / "incidents.parquet"
RELATIONSHIPS_FILE = Path("incidents") / "incident_relationships.parquet"
REVIEW_PACK_FILE = Path("incidents") / "incident_review_pack.parquet"
TIMELINE_FILE = Path("incidents") / "incident_timeline.parquet"
SUMMARY_FILE = Path("incidents") / "incident_summary.parquet"
ACTIONS_FILE = Path("incidents") / "recommended_actions.parquet"
SUPPRESSED_FILE = Path("incidents") / "suppressed_duplicate_events.parquet"
UNSUPPORTED_FILE = Path("incidents") / "unsupported_incident_sources.parquet"
REPORT_MD = "incidents_report.md"
FINDINGS_JSON = "incidents_findings.json"

# Upstream run-internal contracts (read-only).
DRIFT_MANIFEST = drift_io.MANIFEST_NAME
SENSOR_HEALTH_MANIFEST = drift_io.SENSOR_HEALTH_MANIFEST
ANOMALY_MANIFEST = drift_io.ANOMALY_MANIFEST
OPERATIONAL_MANIFEST = drift_io.OPERATIONAL_MANIFEST
BOM_MANIFEST = "bom_context_manifest.json"


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


def load_drift_artifacts(
    drift_run: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drift events + raw-vs-healthy comparison from a completed drift run."""
    events = _parse_timestamps(
        pd.read_parquet(drift_run / drift_io.EVENTS_FILE),
        ("start_timestamp", "end_timestamp"),
    )
    comparison = _parse_timestamps(
        pd.read_parquet(drift_run / drift_io.RAW_VS_HEALTHY_FILE),
        ("window_start",),
    )
    return events, comparison


def load_sensor_health_events(
    sensor_health_run: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sensor-health events + quarantine recommendations (read-only)."""
    events = _parse_timestamps(
        pd.read_parquet(sensor_health_run / "events" / "sensor_health_events.parquet"),
        ("start_timestamp", "end_timestamp"),
    )
    quarantine = _parse_timestamps(
        pd.read_parquet(
            sensor_health_run / "summaries" / "quarantine_recommendations.parquet"
        ),
        ("start_timestamp", "end_timestamp"),
    )
    return events, quarantine


def load_anomaly_scores(anomaly_run: Path) -> pd.DataFrame:
    """Per-row anomaly scores, timestamp-indexed (severity + attribution)."""
    return drift_io.load_anomaly_scores(anomaly_run)


def load_operational_artifacts(
    operational_run: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Operational context timeline + transition events (read-only)."""
    timeline = drift_io.load_operational_timeline(operational_run)
    transitions = _parse_timestamps(
        pd.read_parquet(
            operational_run / "transitions" / "context_transition_events.parquet"
        ),
        ("transition_timestamp",),
    )
    return timeline, transitions


def load_bom_transitions(bom_run: Path) -> pd.DataFrame:
    """BOM order transitions (read-only)."""
    return _parse_timestamps(
        pd.read_parquet(bom_run / "orders" / "bom_order_transitions.parquet"),
        ("transition_timestamp",),
    )
