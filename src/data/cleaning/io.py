"""CSV loader for ``data/raw/Dades_pellet.csv``.

The raw file has a three-row header:
  Row 0  Spanish descriptions
  Row 1  PLC codes (used as the actual column identifier)
  Row 2  Units

And uses **comma decimal separator** (Spanish locale: ``"2,9"`` → ``2.9``).

This loader returns a :class:`pandas.DataFrame` with **logical** column
names (e.g. ``conditioner_inlet_temp`` instead of ``E1172_1``), as defined
in ``data/features/data_pellets_dictionary.csv``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "Dades_pellet.csv"
DEFAULT_DICTIONARY = (
    PROJECT_ROOT / "data" / "features" / "data_pellets_dictionary.csv"
)

TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


def _plc_code_to_logical_name(dictionary_path: Path) -> dict[str, str]:
    """Build PLC-code → logical-variable-name map from the dictionary CSV."""
    df = pd.read_csv(dictionary_path)
    return dict(zip(df["Sensor"].astype(str), df["Variable"].astype(str)))


def load_raw(
    csv_path: Path = DEFAULT_RAW,
    dictionary_path: Path = DEFAULT_DICTIONARY,
) -> pd.DataFrame:
    """Load the raw pellet CSV into a typed DataFrame.

    Returns
    -------
    pandas.DataFrame
        Columns renamed to logical variable names.
        ``timestamp`` parsed to ``datetime64[ns]``.
        Numeric columns parsed with comma-as-decimal-separator.
        Categorical identifier columns kept as strings.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw CSV not found at {csv_path}")

    # Three-row header in the source file:
    #   0: Spanish descriptions   → skip
    #   1: PLC codes              → use as header (becomes row 0 after skiprows)
    #   2: Units                  → skip
    df = pd.read_csv(
        csv_path,
        header=0,
        skiprows=[0, 2],
        decimal=",",
        dtype=str,
        keep_default_na=True,
        na_values=["", "NaN", "nan", "NULL", "null", "None"],
    )

    code_to_name = _plc_code_to_logical_name(dictionary_path)
    rename_map: dict[str, str] = {}
    for col in df.columns:
        if col in code_to_name:
            rename_map[col] = code_to_name[col]
    df = df.rename(columns=rename_map)

    if "timestamp" not in df.columns:
        raise ValueError(
            "Expected 'timestamp' column after renaming PLC codes; "
            "check that data_pellets_dictionary.csv is up to date."
        )

    # Parse timestamp; coerce bad cells to NaT (caught by timestamps module)
    df["timestamp"] = _parse_timestamps(df["timestamp"])

    # Coerce numeric columns; ID columns stay as strings.
    # Source values use Spanish locale (comma decimal); we read as str above
    # because pandas only applies decimal="," when actually parsing numerics.
    id_cols = {"work_order", "deposit_equipment_id", "batch_id", "batch_quality_id"}
    for col in df.columns:
        if col == "timestamp" or col in id_cols:
            continue
        s = df[col].astype("string").str.replace(",", ".", regex=False)
        df[col] = pd.to_numeric(s, errors="coerce")

    return df


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Try a few datetime formats; return NaT for unparseable cells."""
    parsed = pd.to_datetime(series, format=TIMESTAMP_FORMATS[0], errors="coerce")
    mask = parsed.isna() & series.notna()
    if mask.any():
        fallback = pd.to_datetime(
            series[mask], format=TIMESTAMP_FORMATS[1], errors="coerce"
        )
        parsed.loc[mask] = fallback
    return parsed


def write_clean(df: pd.DataFrame, out_path: Path) -> None:
    """Persist the cleaned DataFrame as a flat CSV (UTF-8, dot decimal)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
