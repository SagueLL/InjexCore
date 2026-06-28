"""I/O helpers and output layout for the BOM Operational Context Layer.

Outputs are run-versioned — every execution writes into a fresh
``data/context/bom/runs/<run_id>/`` directory and never overwrites an
earlier run (run machinery shared with the Intelligence Layer)::

    data/context/bom/runs/<run_id>/
    ├── normalized/
    │   ├── bom_components.parquet       one row per BOM component (Stage B)
    │   ├── bom_rejected_rows.parquet    rejected raw rows + explicit reason
    │   └── bom_duplicate_rows.parquet   duplicate raw rows + explicit reason
    ├── orders/
    │   ├── bom_orders.parquet           one row per production order (Stage C)
    │   ├── bom_order_overlaps.parquet   concurrent-order windows (Stage D)
    │   ├── bom_order_gaps.parquet       uncovered windows inside coverage
    │   └── bom_order_transitions.parquet  classified order-to-order changes
    ├── timeline/
    │   └── bom_context_timeline.parquet one row per master timestamp (Stage E)
    ├── summaries/
    │   ├── bom_product_summary.parquet
    │   ├── bom_recipe_summary.parquet
    │   ├── bom_signature_summary.parquet
    │   └── bom_context_coverage.parquet
    ├── forensics/
    │   └── bom_forensic_event_context.parquet  candidate-date context (Stage G)
    ├── bom_quality_report.md            Stage A raw-quality narrative
    ├── bom_context_report.md            production-context narrative
    ├── bom_context_findings.json        full ``Finding`` report
    └── bom_context_manifest.json        written LAST — marks the run complete

The Stage H addendum writes separately under
``data/intelligence/forensics/bom_addenda/<run_id>/`` (see
:mod:`src.context.bom.forensic_addendum`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

# Shared run-versioning + table/manifest writers. TODO(debt): these live in
# src/intelligence/_common but are layer-agnostic; move to a neutral shared
# package when a third consumer appears (same note as the intelligence shims).
from src.config import CONTEXT_DIR, INTELLIGENCE_DIR, PROJECT_ROOT
from src.context.bom.policy import RawInputPolicy
from src.intelligence._common.io import write_manifest, write_table
from src.intelligence._common.runs import (
    LATEST,
    create_run_dir,
    new_run_id,
    resolve_run,
    run_dir,
)

__all__ = [
    "BOM_DIR",
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
    "read_raw_csv",
    "file_sha256",
    "load_master_timestamps",
    "resolve_project_path",
]

BOM_DIR = CONTEXT_DIR / "bom"
ADDENDA_DIR = INTELLIGENCE_DIR / "forensics" / "bom_addenda"

MANIFEST_NAME = "bom_context_manifest.json"
ADDENDUM_MANIFEST_NAME = "bom_addendum_manifest.json"

COMPONENTS_FILE = Path("normalized") / "bom_components.parquet"
REJECTED_FILE = Path("normalized") / "bom_rejected_rows.parquet"
DUPLICATES_FILE = Path("normalized") / "bom_duplicate_rows.parquet"

ORDERS_FILE = Path("orders") / "bom_orders.parquet"
OVERLAPS_FILE = Path("orders") / "bom_order_overlaps.parquet"
GAPS_FILE = Path("orders") / "bom_order_gaps.parquet"
TRANSITIONS_FILE = Path("orders") / "bom_order_transitions.parquet"

TIMELINE_FILE = Path("timeline") / "bom_context_timeline.parquet"

PRODUCT_SUMMARY_FILE = Path("summaries") / "bom_product_summary.parquet"
RECIPE_SUMMARY_FILE = Path("summaries") / "bom_recipe_summary.parquet"
SIGNATURE_SUMMARY_FILE = Path("summaries") / "bom_signature_summary.parquet"
COVERAGE_FILE = Path("summaries") / "bom_context_coverage.parquet"

EVENT_CONTEXT_FILE = Path("forensics") / "bom_forensic_event_context.parquet"

QUALITY_REPORT_MD = "bom_quality_report.md"
CONTEXT_REPORT_MD = "bom_context_report.md"
FINDINGS_JSON = "bom_context_findings.json"


def resolve_project_path(path_str: str) -> Path:
    """Resolve a policy path string relative to the project root."""
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_raw_csv(path: Path, policy: RawInputPolicy) -> pd.DataFrame:
    """Load the raw BOM CSV with every column as ``str`` (no silent coercion).

    Adds ``source_row_number`` (1-based data-row index, header excluded) and
    ``source_file`` so every downstream row stays traceable to its origin.
    """
    if not path.exists():
        raise FileNotFoundError(f"Raw BOM CSV not found at {path}")
    raw = pd.read_csv(path, encoding=policy.encoding, sep=policy.delimiter, dtype=str)
    raw["source_row_number"] = range(1, len(raw) + 1)
    raw["source_file"] = path.name
    return raw


def file_sha256(path: Path) -> str:
    """Streaming sha256 of a file's bytes (1 MiB chunks)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_master_timestamps(path: Path) -> pd.DatetimeIndex:
    """Load only the master dataset's timestamp column (566-col file).

    Column-projected parquet read — the BOM layer never needs (and never
    touches) the sensor columns.
    """
    if not path.exists():
        raise FileNotFoundError(f"Master dataset not found at {path}")
    frame = pd.read_parquet(path, columns=["timestamp"])
    ts = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], errors="raise"))
    ts.name = "timestamp"
    return ts
