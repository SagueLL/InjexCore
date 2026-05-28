"""I/O helpers for the time-series engineering pipeline.

Input: the cleaned CSV produced by :mod:`src.data.cleaning`.
Output: a wide feature matrix written as Parquet (primary) and optionally
CSV (mirror). Parquet is preferred because the matrix grows to several
hundred columns after the rolling/lag explosion — Parquet is columnar,
typed and roughly an order of magnitude smaller on disk.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLEAN_IN = PROJECT_ROOT / "data" / "processed" / "Dades_pellet_clean.csv"
DEFAULT_FEATURES = PROJECT_ROOT / "data" / "features" / "Dades_pellet_features.parquet"


def load_clean(csv_path: Path = DEFAULT_CLEAN_IN) -> pd.DataFrame:
    """Load the cleaned CSV with ``timestamp`` parsed to ``datetime64[ns]``.

    The cleaning stage writes the timestamp as ISO-8601 text, so we parse
    it explicitly here. ID columns are kept as strings; everything else is
    left to pandas type inference (the cleaning stage already coerced
    them to ``float64``).
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Cleaned CSV not found at {csv_path}")
    df = pd.read_csv(csv_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def write_features(
    df: pd.DataFrame,
    parquet_path: Path,
    csv_path: Path | None = None,
) -> None:
    """Persist the feature matrix as Parquet, with an optional CSV mirror.

    The ``timestamp`` index (if present) is written as a column so the
    file is loadable standalone without knowledge of the index name.
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    out = df
    if isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index()

    out.to_parquet(parquet_path, index=False)

    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(csv_path, index=False, encoding="utf-8")
