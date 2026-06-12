"""Structural dataset fingerprint: deterministic, drift-sensitive."""

from __future__ import annotations

import pandas as pd
from src.intelligence._common.fingerprint import dataset_fingerprint


def _frame(n_rows: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="60s", name="timestamp")
    return pd.DataFrame({"a": 1.0, "b": 2.0}, index=idx)


def test_deterministic_for_identical_frames() -> None:
    assert (
        dataset_fingerprint(_frame())["sha256"]
        == dataset_fingerprint(_frame())["sha256"]
    )


def test_changes_on_added_column() -> None:
    df = _frame()
    other = df.assign(c=3.0)
    assert dataset_fingerprint(df)["sha256"] != dataset_fingerprint(other)["sha256"]


def test_changes_on_row_count() -> None:
    assert (
        dataset_fingerprint(_frame(5))["sha256"]
        != dataset_fingerprint(_frame(6))["sha256"]
    )


def test_metadata_fields(tmp_path) -> None:
    fp = dataset_fingerprint(_frame(), tmp_path / "master.parquet")
    assert fp["n_rows"] == 5
    assert fp["n_cols"] == 2
    assert fp["index_start"] == "2025-01-01 00:00:00"
    assert fp["source_path"].endswith("master.parquet")
