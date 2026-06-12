"""Behaviour-artifact loaders: strict alignment, missing-artifact errors."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from src.intelligence._common import upstream


def _labels_frame(n_rows: int = 10, n_train: int = 7) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="60s", name="timestamp")
    return pd.DataFrame(
        {
            "profile": ["high_production"] * n_rows,
            "is_train": [1] * n_train + [0] * (n_rows - n_train),
        },
        index=idx,
    )


def test_load_profile_labels_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "profile_labels.parquet"
    _labels_frame().reset_index().to_parquet(path, index=False)
    labels = upstream.load_profile_labels(path)
    assert isinstance(labels.index, pd.DatetimeIndex)
    assert list(labels.columns) == ["profile", "is_train"]


def test_load_profile_labels_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="behaviour component first"):
        upstream.load_profile_labels(tmp_path / "nope.parquet")


def test_load_profile_labels_missing_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    _labels_frame().drop(columns=["is_train"]).reset_index().to_parquet(
        path, index=False
    )
    with pytest.raises(ValueError, match="is_train"):
        upstream.load_profile_labels(path)


def test_align_labels_returns_profile_and_train_mask() -> None:
    labels = _labels_frame()
    df = pd.DataFrame({"x": 1.0}, index=labels.index)
    profile, train_mask = upstream.align_labels(df, labels)
    assert profile.index.equals(df.index)
    assert train_mask.dtype == bool
    assert int(train_mask.sum()) == 7


def test_align_labels_index_mismatch_raises() -> None:
    labels = _labels_frame(10)
    df = pd.DataFrame(
        {"x": 1.0},
        index=pd.date_range("2025-02-01", periods=10, freq="60s", name="timestamp"),
    )
    with pytest.raises(ValueError, match="Re-run the behaviour component"):
        upstream.align_labels(df, labels)
    with pytest.raises(ValueError, match="Re-run the behaviour component"):
        upstream.align_labels(df.iloc[:5], labels)
