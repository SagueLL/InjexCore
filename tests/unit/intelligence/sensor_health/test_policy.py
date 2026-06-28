"""Policy schema, metadata merge and the shipped YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.intelligence.sensor_health.policy import (
    SensorHealthPolicy,
    load_policy,
    resolve_sensor_meta,
)


def test_shipped_yaml_loads_with_expected_overrides(
    sh_policy: SensorHealthPolicy,
) -> None:
    assert sh_policy.features.min_non_null_fraction == 0.0
    meta = resolve_sensor_meta(sh_policy, "inlet_hopper_points")
    assert meta.kind == "counter"
    assert meta.expected_zero_during_profiles == []
    assert "variance_collapse" in meta.disabled_rules
    flow = resolve_sensor_meta(sh_policy, "steam_valve_flow_me2")
    assert len(flow.expected_zero_during_profiles) == 7  # zero normal everywhere
    power = resolve_sensor_meta(sh_policy, "granulator_power")
    assert power.expected_zero_during_profiles == ["stopped", "shutdown"]
    assert power.physical_min == 0.0


def test_defaults_inherit_when_not_overridden(sh_policy: SensorHealthPolicy) -> None:
    meta = resolve_sensor_meta(sh_policy, "conditioner_inlet_temp")  # no override
    assert meta.kind == "process"
    assert meta.allow_flatline_profiles == ["stopped", "shutdown"]
    assert meta.disabled_rules == []


def test_partial_override_merges_field_by_field() -> None:
    policy = SensorHealthPolicy.model_validate(
        {"sensors": {"overrides": {"x": {"kind": "counter"}}}}
    )
    meta = resolve_sensor_meta(policy, "x")
    assert meta.kind == "counter"
    assert meta.allow_flatline_profiles == ["stopped", "shutdown"]  # inherited


def test_unknown_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules:\n  flatline:\n    min_run_rowz: 3\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_policy(bad)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(Path("missing.yaml"))
