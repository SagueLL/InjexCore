"""I/O helpers for the feature engineering pipeline.

Input: the time-series engineering output parquet (preferred) or the
cleaned CSV (fallback when the user wants to skip the ts stage).
Output: a wide engineered feature matrix written as Parquet (primary)
and optionally CSV (mirror).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEATURES_IN = (
    PROJECT_ROOT / "data" / "features" / "Dades_pellet_features.parquet"
)
DEFAULT_ENGINEERED_OUT = (
    PROJECT_ROOT / "data" / "features" / "Dades_pellet_engineered.parquet"
)


def load_features(path: Path = DEFAULT_FEATURES_IN) -> pd.DataFrame:
    """Load the upstream feature matrix.

    Accepts Parquet (the time-series engineering output) or CSV (the
    cleaning output) based on file extension. Returns a DataFrame with
    a :class:`pandas.DatetimeIndex` named ``timestamp`` when a timestamp
    column is present.
    """
    if not path.exists():
        raise FileNotFoundError(f"Feature input not found at {path}")

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index("timestamp")
    return df


def write_engineered(
    df: pd.DataFrame,
    parquet_path: Path,
    csv_path: Path | None = None,
) -> None:
    """Persist the engineered feature matrix as Parquet, optional CSV mirror.

    Any :class:`pandas.DatetimeIndex` is materialised as a column so the
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
