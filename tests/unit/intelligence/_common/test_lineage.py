"""Shared lineage assertions (DAT-01): fingerprint / master-sha / run-pin."""

from __future__ import annotations

import pytest
from src.intelligence._common import lineage


class _Err(RuntimeError):
    """Stand-in for a component's *BlockerError."""


_OWN = {"n_rows": 100, "index_start": "2024-01-01", "index_end": "2024-01-05"}


def test_fingerprint_matches() -> None:
    assert lineage.fingerprint_matches({"dataset_fingerprint": _OWN}, _OWN)
    assert not lineage.fingerprint_matches(
        {"dataset_fingerprint": {**_OWN, "n_rows": 99}}, _OWN
    )
    assert not lineage.fingerprint_matches({}, _OWN)  # no fingerprint -> mismatch


def test_assert_fingerprint_blocks_on_mismatch() -> None:
    lineage.assert_fingerprint("anomaly", {"dataset_fingerprint": _OWN}, _OWN, _Err)
    with pytest.raises(_Err, match="does not match"):
        lineage.assert_fingerprint("anomaly", {}, _OWN, _Err)


def test_assert_master_sha() -> None:
    lineage.assert_master_sha("sh", {"master_dataset_sha256": "abc"}, "abc", _Err)
    with pytest.raises(_Err, match="no master_dataset_sha256"):
        lineage.assert_master_sha("sh", {}, "abc", _Err)
    with pytest.raises(_Err, match="different master"):
        lineage.assert_master_sha("sh", {"master_dataset_sha256": "xyz"}, "abc", _Err)


def test_assert_run_pin() -> None:
    lineage.assert_run_pin("drift", "r1", "r1", _Err)  # exact match -> ok
    lineage.assert_run_pin("drift", None, "r1", _Err)  # absent pin -> unverifiable, ok
    with pytest.raises(_Err, match="divergence"):
        lineage.assert_run_pin("drift", "r1", "r2", _Err)
