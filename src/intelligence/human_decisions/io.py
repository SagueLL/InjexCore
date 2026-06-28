"""I/O helpers and output-path constants for the Human Decision Overlay.

Outputs are **run-versioned** but use the *flat* forensics layout
(``<root>/<run_id>/``) shared by every other forensic artifact
(``reference_decision``, ``drift_addenda``, ...), not the ``runs/<run_id>/``
layout of the fitting components. The manifest is written **last**: its
presence with ``completion_status == "complete"`` marks the run as complete::

    data/intelligence/forensics/human_decisions/<run_id>/
    ├── sensor_quarantine_decisions.parquet     the scoped decision (1 row)
    ├── dashboard_decision_overlay.parquet       compact dashboard overlay (1 row)
    ├── human_adjusted_review_summary.parquet     interpretive-impact summary (1 row)
    ├── required_followup_records.parquet         external records still required
    ├── human_decision_summary.md                 human-readable summary
    └── human_decision_manifest.json              written LAST — completion marker

This module owns no business logic; it re-exports the generic Intelligence-Layer
writers (:func:`write_table`, :func:`write_manifest`) and provides a narrow,
read-only master loader used only to *verify* the realigned boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.config import DATASETS_DIR, INTELLIGENCE_DIR, PROJECT_ROOT
from src.intelligence._common.io import write_manifest, write_table

__all__ = [
    "HUMAN_DECISIONS_DIR",
    "DEFAULT_MASTER_IN",
    "COMPONENT",
    "MANIFEST_NAME",
    "SENSOR_DECISIONS_FILE",
    "DASHBOARD_OVERLAY_FILE",
    "ADJUSTED_REVIEW_FILE",
    "FOLLOWUP_RECORDS_FILE",
    "SUMMARY_MD",
    "RUN_ID_PREFIX",
    "new_run_id",
    "create_run_dir",
    "resolve_project_path",
    "load_boundary_columns",
    "write_table",
    "write_manifest",
]

# --- Output root + flat run layout ----------------------------------------
HUMAN_DECISIONS_DIR = INTELLIGENCE_DIR / "forensics" / "human_decisions"
COMPONENT = "human_decision_overlay"
MANIFEST_NAME = "human_decision_manifest.json"
RUN_ID_PREFIX = "human-decision-v1-"

SENSOR_DECISIONS_FILE = "sensor_quarantine_decisions.parquet"
DASHBOARD_OVERLAY_FILE = "dashboard_decision_overlay.parquet"
ADJUSTED_REVIEW_FILE = "human_adjusted_review_summary.parquet"
FOLLOWUP_RECORDS_FILE = "required_followup_records.parquet"
SUMMARY_MD = "human_decision_summary.md"

# --- Optional read-only verification input --------------------------------
DEFAULT_MASTER_IN = DATASETS_DIR / "master" / "master_dataset.parquet"


def resolve_project_path(path_str: str | Path) -> Path:
    """Resolve a possibly-relative path against the project root."""
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def new_run_id(now: datetime | None = None) -> str:
    """Mint a fresh, self-describing run id: ``human-decision-v1-<UTC ts>``."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{RUN_ID_PREFIX}{stamp}"


def create_run_dir(output_root: Path, run_id: str) -> Path:
    """Create a fresh ``<output_root>/<run_id>/``; never reuse or overwrite."""
    target = output_root / run_id
    target.mkdir(parents=True, exist_ok=False)
    return target


def load_boundary_columns(
    master_path: Path, columns: tuple[str, ...]
) -> pd.DataFrame | None:
    """Read only ``columns`` from the master, read-only; ``None`` if absent.

    Used purely to *verify* the realigned boundary (row index → timestamp and
    the flatline-to-zero of the quarantined channel). Returns ``None`` rather
    than raising when the master is unavailable, so artifact generation never
    depends on the dataset being present (tests / CI run without it).
    """
    if not master_path.exists():
        return None
    return pd.read_parquet(master_path, columns=list(columns))
