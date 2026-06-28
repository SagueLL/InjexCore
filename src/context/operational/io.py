"""Output layout + upstream loading for the Operational Context Overlay.

Outputs are run-versioned — every execution writes into a fresh
``data/context/operational/runs/<run_id>/`` directory and never overwrites
an earlier run::

    data/context/operational/runs/<run_id>/
    ├── timeline/
    │   └── operational_context_timeline.parquet  one row per master timestamp
    ├── transitions/
    │   └── context_transition_events.parquet
    ├── summaries/
    │   ├── steam_context_summary.parquet
    │   ├── sensor_health_context_summary.parquet
    │   ├── bom_context_summary.parquet
    │   └── context_coverage.parquet
    ├── operational_context_report.md
    ├── operational_context_findings.json
    └── operational_context_manifest.json         written LAST — completion marker

The Stage addendum writes separately under
``data/intelligence/forensics/context_addenda/<run_id>/``.
"""

from __future__ import annotations

from pathlib import Path

from src.config import CONTEXT_DIR, INTELLIGENCE_DIR
from src.context.bom.io import file_sha256, resolve_project_path
from src.intelligence._common.io import write_manifest, write_table
from src.intelligence._common.runs import (
    LATEST,
    create_run_dir,
    new_run_id,
    resolve_run,
    run_dir,
)
from src.intelligence.sensor_health.io import load_master_columns

__all__ = [
    "OPERATIONAL_DIR",
    "ADDENDA_DIR",
    "MANIFEST_NAME",
    "ADDENDUM_MANIFEST_NAME",
    "LATEST",
    "new_run_id",
    "resolve_run",
    "run_dir",
    "create_run_dir",
    "write_manifest",
    "write_table",
    "file_sha256",
    "resolve_project_path",
    "load_master_columns",
]

OPERATIONAL_DIR = CONTEXT_DIR / "operational"
ADDENDA_DIR = INTELLIGENCE_DIR / "forensics" / "context_addenda"

MANIFEST_NAME = "operational_context_manifest.json"
ADDENDUM_MANIFEST_NAME = "context_addendum_manifest.json"

TIMELINE_FILE = Path("timeline") / "operational_context_timeline.parquet"
TRANSITIONS_FILE = Path("transitions") / "context_transition_events.parquet"
STEAM_SUMMARY_FILE = Path("summaries") / "steam_context_summary.parquet"
HEALTH_SUMMARY_FILE = Path("summaries") / "sensor_health_context_summary.parquet"
BOM_SUMMARY_FILE = Path("summaries") / "bom_context_summary.parquet"
COVERAGE_FILE = Path("summaries") / "context_coverage.parquet"
REPORT_MD = "operational_context_report.md"
FINDINGS_JSON = "operational_context_findings.json"

SENSOR_HEALTH_MANIFEST = "sensor_health_manifest.json"
BOM_MANIFEST = "bom_context_manifest.json"
