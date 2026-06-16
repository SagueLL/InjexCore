"""Output layout + column-projected input loading for Sensor Health.

Outputs are run-versioned — every execution writes into a fresh
``data/intelligence/sensor_health/runs/<run_id>/`` directory and never
overwrites an earlier run (see :mod:`src.intelligence._common.runs`)::

    data/intelligence/sensor_health/runs/<run_id>/
    ├── scores/
    │   └── sensor_health_scores.parquet      per (timestamp, sensor) status
    ├── events/
    │   └── sensor_health_events.parquet      aggregated issue episodes
    ├── summaries/
    │   ├── sensor_health_summary.parquet     one row per sensor
    │   ├── sensor_quality_timeline.parquet   per-timestamp context (consumed
    │   │                                     by the Operational Context layer)
    │   ├── quarantine_recommendations.parquet  approval_required=true always
    │   └── unsupported_sensors.parquet       (sensor, profile, reason)
    ├── sensor_health_report.md
    ├── sensor_health_findings.json
    └── sensor_health_manifest.json           written LAST — marks completion
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.config import INTELLIGENCE_DIR
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

__all__ = [
    "SENSOR_HEALTH_DIR",
    "MANIFEST_NAME",
    "DEFAULT_MASTER_IN",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "create_run_dir",
    "write_manifest",
    "write_table",
    "load_master_columns",
]

SENSOR_HEALTH_DIR = INTELLIGENCE_DIR / "sensor_health"

MANIFEST_NAME = "sensor_health_manifest.json"
SCORES_FILE = Path("scores") / "sensor_health_scores.parquet"
EVENTS_FILE = Path("events") / "sensor_health_events.parquet"
SUMMARY_FILE = Path("summaries") / "sensor_health_summary.parquet"
QUALITY_TIMELINE_FILE = Path("summaries") / "sensor_quality_timeline.parquet"
QUARANTINE_FILE = Path("summaries") / "quarantine_recommendations.parquet"
UNSUPPORTED_FILE = Path("summaries") / "unsupported_sensors.parquet"
REPORT_MD = "sensor_health_report.md"
FINDINGS_JSON = "sensor_health_findings.json"


def load_master_columns(path: Path, columns: list[str]) -> pd.DataFrame:
    """Column-projected master read (566-col file; we need ~17 sensors).

    Loads ``timestamp`` + every requested column that exists in the file,
    parsed and timestamp-indexed like ``load_master``. Missing columns are
    simply absent from the result — the feature selector reports them.
    """
    if not path.exists():
        raise FileNotFoundError(f"Master dataset not found at {path}")
    available = set(pq.ParquetFile(path).schema_arrow.names)
    wanted = ["timestamp"] + [c for c in columns if c in available]
    df = pd.read_parquet(path, columns=[c for c in wanted if c in available])
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index("timestamp")
    return df
