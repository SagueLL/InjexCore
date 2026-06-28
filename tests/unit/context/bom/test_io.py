"""Raw CSV reading, hashing and master timestamp loading."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from src.context.bom import io
from src.context.bom.policy import BomContextPolicy


def _write_csv(path: Path, factory: Callable[..., pd.DataFrame]) -> pd.DataFrame:
    frame = factory([{}, {"order_id": "101"}])
    source = frame.drop(columns=["source_row_number", "source_file"])
    source.to_csv(path, index=False, encoding="utf-8-sig")
    return source


def test_read_raw_csv_str_dtypes_and_traceability(
    tmp_path: Path,
    raw_bom_factory: Callable[..., pd.DataFrame],
    bom_policy: BomContextPolicy,
) -> None:
    path = tmp_path / "bom.csv"
    _write_csv(path, raw_bom_factory)
    raw = io.read_raw_csv(path, bom_policy.raw_input)
    # utf-8-sig BOM stripped: first header is clean
    assert raw.columns[0] == "EQ56_ORDRE"
    data_cols = [
        c for c in raw.columns if c not in ("source_row_number", "source_file")
    ]
    assert all(raw[c].map(lambda v: isinstance(v, str)).all() for c in data_cols)
    assert raw["Porcentaje"].iloc[0] == "60,5"  # comma decimal untouched here
    assert list(raw["source_row_number"]) == [1, 2]
    assert set(raw["source_file"]) == {"bom.csv"}


def test_read_raw_csv_missing_file_raises(bom_policy: BomContextPolicy) -> None:
    with pytest.raises(FileNotFoundError):
        io.read_raw_csv(Path("missing.csv"), bom_policy.raw_input)


def test_file_sha256_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"injexcore" * 1000)
    assert io.file_sha256(path) == hashlib.sha256(b"injexcore" * 1000).hexdigest()


def test_load_master_timestamps_roundtrip(tmp_path: Path) -> None:
    ts = pd.date_range("2024-09-01", periods=10, freq="1h")
    frame = pd.DataFrame({"timestamp": ts, "sensor": range(10)})
    path = tmp_path / "master.parquet"
    frame.to_parquet(path, index=False)
    loaded = io.load_master_timestamps(path)
    assert isinstance(loaded, pd.DatetimeIndex)
    assert (loaded == pd.DatetimeIndex(ts)).all()


def test_run_constants_are_relative() -> None:
    assert not io.COMPONENTS_FILE.is_absolute()
    assert io.MANIFEST_NAME == "bom_context_manifest.json"
