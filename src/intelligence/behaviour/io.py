"""I/O helpers and output-path constants for the Behaviour Intelligence stage.

Input: the schema-locked master dataset
(``data/datasets/master/master_dataset.parquet``).

Outputs are **run-versioned** — every execution writes into a fresh
``data/intelligence/behaviour/runs/<run_id>/`` directory and never overwrites
an earlier run (see :mod:`src.intelligence._common.runs`). The fit manifest is
written **last**: its presence marks the run as complete and resolvable::

    data/intelligence/behaviour/runs/<run_id>/
    ├── profiles/
    │   └── profile_labels.parquet         per-row regime label (+ material-change flag)
    ├── baselines/
    │   └── baselines.parquet              long-form per-(profile, sensor) statistics
    ├── validation/
    │   ├── distribution.parquet           per-profile row counts / coverage
    │   ├── durations.parquet              per-profile contiguous-segment statistics
    │   └── transitions.parquet            profile->profile transition counts
    ├── behaviour_intelligence_report.{json,md}   ``Finding`` report
    └── behaviour_fit_manifest.json        written LAST — the reproducible fit
                                           contract (train window, master sha,
                                           sensor list) downstream consumes

Downstream components resolve the latest *completed* behaviour run via
:func:`src.intelligence._common.upstream.resolve_behaviour_run`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import DATASETS_DIR, INTELLIGENCE_DIR
from src.intelligence._common.fingerprint import file_sha256
from src.intelligence._common.runs import (
    LATEST,
    create_run_dir,
    new_run_id,
    resolve_run,
    run_dir,
)

__all__ = [
    "DEFAULT_MASTER_IN",
    "BEHAVIOUR_DIR",
    "COMPONENT",
    "MANIFEST_NAME",
    "PROFILE_LABELS_FILE",
    "BASELINES_FILE",
    "DISTRIBUTION_FILE",
    "DURATIONS_FILE",
    "TRANSITIONS_FILE",
    "REPORT_JSON",
    "REPORT_MD",
    "LATEST",
    "new_run_id",
    "create_run_dir",
    "run_dir",
    "resolve_run",
    "file_sha256",
    "load_master",
    "write_table",
    "write_manifest",
]

# --- Input ----------------------------------------------------------------
DEFAULT_MASTER_IN = DATASETS_DIR / "master" / "master_dataset.parquet"

# --- Output root + run-versioned layout -----------------------------------
BEHAVIOUR_DIR = INTELLIGENCE_DIR / "behaviour"
COMPONENT = "behaviour"

MANIFEST_NAME = "behaviour_fit_manifest.json"

# Run-relative artifact paths (one subfolder per family, mirroring the
# datasets-stage convention). Writers mkdir parents on write.
PROFILE_LABELS_FILE = Path("profiles") / "profile_labels.parquet"
BASELINES_FILE = Path("baselines") / "baselines.parquet"
DISTRIBUTION_FILE = Path("validation") / "distribution.parquet"
DURATIONS_FILE = Path("validation") / "durations.parquet"
TRANSITIONS_FILE = Path("validation") / "transitions.parquet"
REPORT_JSON = "behaviour_intelligence_report.json"
REPORT_MD = "behaviour_intelligence_report.md"


def load_master(path: Path = DEFAULT_MASTER_IN) -> pd.DataFrame:
    """Load the master dataset.

    Accepts Parquet (preferred) or CSV by extension. When a ``timestamp``
    column is present it is parsed and promoted to a
    :class:`pandas.DatetimeIndex` so profile segmentation and validation can
    reason about time order and segment durations.
    """
    if not path.exists():
        raise FileNotFoundError(f"Master dataset not found at {path}")

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index("timestamp")
    return df


def write_table(df: pd.DataFrame, path: Path) -> None:
    """Persist a DataFrame artifact as Parquet.

    A :class:`~pandas.DatetimeIndex` is materialised as a column so the file
    is loadable standalone (mirrors the datasets-stage writer).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df
    if isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index()
    out.to_parquet(path, index=False)


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write the fit manifest as indented, UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
