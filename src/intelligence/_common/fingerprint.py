"""Structural dataset fingerprint for fit manifests.

A cheap O(columns) identity for "which dataset was this fitted on": the
sha256 of row count, column names, dtypes and index span. Catches schema
drift, re-cleaned data and changed time windows; deliberately *not* a
byte-level file hash (slow on large parquet, and breaks on metadata-only
rewrites of identical content).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


def dataset_fingerprint(
    df: pd.DataFrame, source_path: Path | None = None
) -> dict[str, Any]:
    """Structural fingerprint of ``df`` as a JSON-serialisable dict."""
    index_start = index_end = None
    if isinstance(df.index, pd.DatetimeIndex) and len(df):
        index_start = str(df.index.min())
        index_end = str(df.index.max())

    parts = [
        str(len(df)),
        str(df.shape[1]),
        ",".join(map(str, df.columns)),
        ",".join(str(dt) for dt in df.dtypes),
        str(index_start),
        str(index_end),
    ]
    sha = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return {
        "sha256": sha,
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "index_start": index_start,
        "index_end": index_end,
        "source_path": str(source_path) if source_path is not None else None,
    }
