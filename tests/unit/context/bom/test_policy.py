"""Policy schema and YAML loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.context.bom.policy import BomContextPolicy, load_policy


def test_shipped_yaml_loads_with_expected_values(
    bom_policy: BomContextPolicy,
) -> None:
    assert bom_policy.raw_input.columns.start_timestamp == "Fecha Incio"
    assert bom_policy.raw_input.encoding == "utf-8-sig"
    assert bom_policy.raw_input.decimal_comma is True
    assert bom_policy.timeline.expected_master_rows == 167331
    assert bom_policy.percentage.expected_min == 99.0
    assert bom_policy.percentage.expected_max == 103.0
    assert bom_policy.forensic_addendum.anomaly_run_id == "20260611T173316Z"
    assert "2024-09-16" in bom_policy.forensic_windows.candidate_dates


def test_unknown_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("percentage:\n  expected_minn: 99.0\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_policy(bad)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(Path("does/not/exist.yaml"))


def test_defaults_construct_without_yaml() -> None:
    policy = BomContextPolicy()
    assert policy.signature.hash_prefix_len == 16
    assert policy.timeline.boundary == "closed_open"
