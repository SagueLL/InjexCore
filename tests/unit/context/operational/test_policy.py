"""Policy schema and the shipped YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.context.operational.policy import OperationalContextPolicy, load_policy


def test_shipped_yaml_loads_with_expected_pins(
    op_policy: OperationalContextPolicy,
) -> None:
    assert op_policy.timeline.expected_master_rows == 167331
    assert op_policy.upstream.bom_run == "20260612T124909Z"
    assert op_policy.upstream.anomaly_run == "20260611T173316Z"
    assert op_policy.upstream.sensor_health_run == "latest"
    assert op_policy.steam.pressure_active_threshold == 1.0
    assert op_policy.steam.temp_active_threshold == 60.0
    assert op_policy.steam.window_rows == 241
    assert "2024-09-16" in op_policy.forensic_addendum.candidate_dates


def test_unknown_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("steam:\n  presure_active_threshold: 1.0\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_policy(bad)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(Path("missing.yaml"))
