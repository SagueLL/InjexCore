"""I/O helpers and output-path constants for the Behaviour Intelligence stage.

Input: the schema-locked master dataset
(``data/datasets/master/master_dataset.parquet``).

Outputs (all under ``data/intelligence/behaviour/`` — git-ignored, like the
rest of ``data/``). Grouped into one subfolder per artifact family, mirroring
the ``data/datasets/{master,specialized}/`` convention; the component-level
fit manifest and ``Finding`` report sit at the behaviour root::

    data/intelligence/behaviour/
    ├── profiles/
    │   └── profile_labels.parquet         per-row regime label (+ material-change flag)
    ├── baselines/
    │   └── baselines.parquet              long-form per-(profile, sensor) statistics
    ├── validation/
    │   ├── distribution.parquet           per-profile row counts / coverage
    │   ├── durations.parquet              per-profile contiguous-segment statistics
    │   └── transitions.parquet            profile->profile transition counts
    ├── behaviour_fit_manifest.json        train-window bounds, production quantile
    │                                      edges, sensor list, fit timestamp — the
    │                                      reproducible fit contract for scoring
    └── behaviour_intelligence_report.{json,md}   ``Finding`` report
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import DATASETS_DIR, INTELLIGENCE_DIR

# --- Input ----------------------------------------------------------------
DEFAULT_MASTER_IN = DATASETS_DIR / "master" / "master_dataset.parquet"

# --- Output root ----------------------------------------------------------
BEHAVIOUR_DIR = INTELLIGENCE_DIR / "behaviour"

# Artifacts — one subfolder per family (writers mkdir parents on write).
DEFAULT_PROFILE_LABELS_OUT = BEHAVIOUR_DIR / "profiles" / "profile_labels.parquet"
DEFAULT_BASELINES_OUT = BEHAVIOUR_DIR / "baselines" / "baselines.parquet"
DEFAULT_DISTRIBUTION_OUT = BEHAVIOUR_DIR / "validation" / "distribution.parquet"
DEFAULT_DURATIONS_OUT = BEHAVIOUR_DIR / "validation" / "durations.parquet"
DEFAULT_TRANSITIONS_OUT = BEHAVIOUR_DIR / "validation" / "transitions.parquet"

# Component-level summaries at the behaviour root (span all families).
DEFAULT_FIT_MANIFEST_OUT = BEHAVIOUR_DIR / "behaviour_fit_manifest.json"
DEFAULT_REPORT_JSON = BEHAVIOUR_DIR / "behaviour_intelligence_report.json"
DEFAULT_REPORT_MD = BEHAVIOUR_DIR / "behaviour_intelligence_report.md"


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
