"""I/O helpers and output-path constants for the specialized-datasets stage.

Input: the feature-engineering output parquet
(``data/features/Dades_pellet_engineered.parquet``).

Outputs (one parquet + one JSON + one Markdown per dataset):

* Master       → ``data/datasets/master/master_dataset.parquet``
* Anomaly      → ``data/datasets/specialized/anomaly_detection_dataset.parquet``
* Forecasting  → ``data/datasets/specialized/forecasting_dataset.parquet``
* Energy       → ``data/datasets/specialized/energy_dataset.parquet``
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# --- Inputs ---------------------------------------------------------------
DEFAULT_ENGINEERED_IN = (
    PROJECT_ROOT / "data" / "features" / "Dades_pellet_engineered.parquet"
)

# --- Master ---------------------------------------------------------------
MASTER_DIR = PROJECT_ROOT / "data" / "datasets" / "master"
DEFAULT_MASTER_OUT = MASTER_DIR / "master_dataset.parquet"
DEFAULT_MASTER_REPORT_JSON = MASTER_DIR / "master_dataset_report.json"
DEFAULT_MASTER_REPORT_MD = MASTER_DIR / "master_dataset_report.md"
DEFAULT_SCHEMA_LOCK = MASTER_DIR / "schema_lock.json"

# --- Specialized ----------------------------------------------------------
SPECIALIZED_DIR = PROJECT_ROOT / "data" / "datasets" / "specialized"

DEFAULT_ANOMALY_OUT = SPECIALIZED_DIR / "anomaly_detection_dataset.parquet"
DEFAULT_ANOMALY_REPORT_JSON = (
    SPECIALIZED_DIR / "anomaly_detection_dataset_report.json"
)
DEFAULT_ANOMALY_REPORT_MD = (
    SPECIALIZED_DIR / "anomaly_detection_dataset_report.md"
)

DEFAULT_FORECASTING_OUT = SPECIALIZED_DIR / "forecasting_dataset.parquet"
DEFAULT_FORECASTING_REPORT_JSON = (
    SPECIALIZED_DIR / "forecasting_dataset_report.json"
)
DEFAULT_FORECASTING_REPORT_MD = (
    SPECIALIZED_DIR / "forecasting_dataset_report.md"
)

DEFAULT_ENERGY_OUT = SPECIALIZED_DIR / "energy_dataset.parquet"
DEFAULT_ENERGY_REPORT_JSON = SPECIALIZED_DIR / "energy_dataset_report.json"
DEFAULT_ENERGY_REPORT_MD = SPECIALIZED_DIR / "energy_dataset_report.md"


def load_engineered(path: Path = DEFAULT_ENGINEERED_IN) -> pd.DataFrame:
    """Load the upstream engineered feature matrix.

    Accepts Parquet (preferred) or CSV based on file extension. When a
    ``timestamp`` column is present it is parsed and promoted to a
    :class:`pandas.DatetimeIndex` so projections preserve the index.
    """
    if not path.exists():
        raise FileNotFoundError(f"Engineered input not found at {path}")

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index("timestamp")
    return df


def write_dataset(df: pd.DataFrame, parquet_path: Path) -> None:
    """Persist a dataset as Parquet, materialising the timestamp index as
    a column so the file is loadable standalone."""
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    out = df
    if isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index()
    out.to_parquet(parquet_path, index=False)
