"""Output layout + upstream-run loading for Drift Intelligence.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/drift/runs/<run_id>/`` directory and never overwrites an
earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/drift/runs/<run_id>/
    ├── scores/
    │   └── drift_scores.parquet              per (window, scope, view, entity, profile)
    ├── events/
    │   └── drift_events.parquet              aggregated drift episodes (pending_review)
    ├── summaries/
    │   ├── sensor_drift_summary.parquet
    │   ├── profile_drift_summary.parquet
    │   ├── context_drift_summary.parquet
    │   ├── correlation_drift_summary.parquet
    │   ├── multivariate_drift_summary.parquet
    │   ├── profile_composition_shift.parquet
    │   ├── steam_context_shift.parquet
    │   ├── sensor_health_context_shift.parquet
    │   ├── bom_context_shift.parquet
    │   ├── raw_vs_healthy_only_comparison.parquet
    │   └── unsupported_scopes.parquet
    ├── drift_report.md
    ├── drift_findings.json
    └── drift_manifest.json                   written LAST — marks completion

All upstream loading is strictly read-only: persisted runs are consumed as
files, never re-fitted, never modified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import INTELLIGENCE_DIR, PROJECT_ROOT
from src.intelligence._common.fingerprint import file_sha256
from src.intelligence._common.io import (
    DEFAULT_MASTER_IN,
    write_manifest,
    write_table,
)
from src.intelligence._common.runs import (
    LATEST,
    create_run_dir,
    new_run_id,
    resolve_run,
    run_dir,
)
from src.intelligence.sensor_health.io import load_master_columns

__all__ = [
    "DRIFT_DIR",
    "MANIFEST_NAME",
    "DEFAULT_MASTER_IN",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "create_run_dir",
    "write_manifest",
    "write_table",
    "file_sha256",
    "load_master_columns",
    "resolve_project_path",
    "load_run_manifest",
    "load_anomaly_scores",
    "load_pca_artifacts",
    "load_correlation_artifacts",
    "load_sensor_health_artifacts",
    "load_operational_timeline",
    "build_exclusion_mask",
]

DRIFT_DIR = INTELLIGENCE_DIR / "drift"

MANIFEST_NAME = "drift_manifest.json"
SCORES_FILE = Path("scores") / "drift_scores.parquet"
EVENTS_FILE = Path("events") / "drift_events.parquet"
SENSOR_SUMMARY_FILE = Path("summaries") / "sensor_drift_summary.parquet"
PROFILE_SUMMARY_FILE = Path("summaries") / "profile_drift_summary.parquet"
CONTEXT_SUMMARY_FILE = Path("summaries") / "context_drift_summary.parquet"
CORRELATION_SUMMARY_FILE = Path("summaries") / "correlation_drift_summary.parquet"
MULTIVARIATE_SUMMARY_FILE = Path("summaries") / "multivariate_drift_summary.parquet"
PROFILE_COMPOSITION_FILE = Path("summaries") / "profile_composition_shift.parquet"
STEAM_SHIFT_FILE = Path("summaries") / "steam_context_shift.parquet"
SENSOR_HEALTH_SHIFT_FILE = Path("summaries") / "sensor_health_context_shift.parquet"
BOM_SHIFT_FILE = Path("summaries") / "bom_context_shift.parquet"
RAW_VS_HEALTHY_FILE = Path("summaries") / "raw_vs_healthy_only_comparison.parquet"
UNSUPPORTED_FILE = Path("summaries") / "unsupported_scopes.parquet"
REPORT_MD = "drift_report.md"
FINDINGS_JSON = "drift_findings.json"

# Upstream run-internal layouts (read-only contracts).
ANOMALY_MANIFEST = "anomaly_fit_manifest.json"
PCA_MANIFEST = "pca_fit_manifest.json"
CORRELATION_MANIFEST = "correlation_fit_manifest.json"
SENSOR_HEALTH_MANIFEST = "sensor_health_manifest.json"
OPERATIONAL_MANIFEST = "operational_context_manifest.json"


def resolve_project_path(path_str: str) -> Path:
    """Resolve a policy path string against the project root."""
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _timestamp_indexed(df: pd.DataFrame) -> pd.DataFrame:
    """Promote a materialised ``timestamp`` column back to the index."""
    if "timestamp" in df.columns:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index("timestamp")
    return df


def load_run_manifest(run_dir_path: Path, manifest_name: str) -> dict[str, Any]:
    """Load a completed upstream run's manifest."""
    path = run_dir_path / manifest_name
    if not path.exists():
        raise FileNotFoundError(f"Upstream manifest not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_anomaly_scores(anomaly_run: Path) -> pd.DataFrame:
    """Per-row anomaly scores from a completed anomaly run, timestamp-indexed."""
    return _timestamp_indexed(
        pd.read_parquet(anomaly_run / "scores" / "anomaly_scores.parquet")
    )


def load_pca_artifacts(pca_run: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Concatenated per-profile pca scores + contributions, timestamp-sorted.

    Returns ``(scores, contributions, skipped_profiles)``. ``recon_error`` is
    renamed to ``reconstruction_error``; a ``profile`` column records which
    per-profile model produced each row. Skipped profiles are reported, never
    NaN-filled.
    """
    scores_root = pca_run / "scores"
    score_frames: list[pd.DataFrame] = []
    contrib_frames: list[pd.DataFrame] = []
    if scores_root.is_dir():
        for profile_dir in sorted(scores_root.iterdir()):
            if not profile_dir.is_dir():
                continue
            scores_path = profile_dir / "scores.parquet"
            if scores_path.exists():
                frame = pd.read_parquet(scores_path)
                frame["profile"] = profile_dir.name
                score_frames.append(frame)
            contrib_path = profile_dir / "contributions.parquet"
            if contrib_path.exists():
                contrib_frames.append(pd.read_parquet(contrib_path))

    skipped: list[str] = []
    skipped_path = pca_run / "skipped_profiles.parquet"
    if skipped_path.exists():
        skipped = pd.read_parquet(skipped_path)["profile"].astype(str).tolist()

    scores = (
        pd.concat(score_frames, ignore_index=True) if score_frames else pd.DataFrame()
    )
    contributions = (
        pd.concat(contrib_frames, ignore_index=True)
        if contrib_frames
        else pd.DataFrame()
    )
    if len(scores):
        scores = scores.rename(columns={"recon_error": "reconstruction_error"})
        scores = _timestamp_indexed(scores).sort_index()
    if len(contributions):
        contributions = _timestamp_indexed(contributions).sort_index()
    return scores, contributions, skipped


def load_correlation_artifacts(
    correlation_run: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train correlation references + train-vs-validation shift table."""
    correlations = pd.read_parquet(correlation_run / "correlations.parquet")
    shift = pd.read_parquet(correlation_run / "correlation_shift.parquet")
    return correlations, shift


def load_sensor_health_artifacts(
    sensor_health_run: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Quality timeline + events + quarantine recommendations (read-only)."""
    timeline = _timestamp_indexed(
        pd.read_parquet(
            sensor_health_run / "summaries" / "sensor_quality_timeline.parquet"
        )
    )
    events = pd.read_parquet(
        sensor_health_run / "events" / "sensor_health_events.parquet"
    )
    for col in ("start_timestamp", "end_timestamp"):
        events[col] = pd.to_datetime(events[col], errors="coerce")
    quarantine = pd.read_parquet(
        sensor_health_run / "summaries" / "quarantine_recommendations.parquet"
    )
    return timeline, events, quarantine


def load_operational_timeline(operational_run: Path) -> pd.DataFrame:
    """Master-aligned operational context timeline, timestamp-indexed."""
    return _timestamp_indexed(
        pd.read_parquet(
            operational_run / "timeline" / "operational_context_timeline.parquet"
        )
    )


_STATUS_COLUMNS = {
    "faulty": "faulty_sensors",
    "warning": "warning_sensors",
    "quarantine_recommended": "quarantine_recommended_sensors",
}


def build_exclusion_mask(
    quality_timeline: pd.DataFrame,
    master_index: pd.DatetimeIndex,
    sensors: list[str],
    exclude_statuses: list[str],
) -> pd.DataFrame:
    """Boolean (timestamp x sensor) frame; ``True`` = analytically excluded.

    Decoded from the sensor-health quality timeline's pipe-joined status
    columns. The mask exists only in memory of this run — upstream artifacts
    are never modified.
    """
    columns = [_STATUS_COLUMNS[s] for s in exclude_statuses if s in _STATUS_COLUMNS]
    aligned = quality_timeline.reindex(master_index)
    mask = pd.DataFrame(False, index=master_index, columns=sensors)
    for col in columns:
        if col not in aligned.columns:
            continue
        joined = aligned[col].fillna("").astype(str)
        for sensor in sensors:
            hits = joined.str.contains(
                rf"(?:^|\|){re.escape(sensor)}(?:\||$)", regex=True
            )
            mask[sensor] = mask[sensor] | hits.to_numpy()
    return mask
