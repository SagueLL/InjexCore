"""CorrelationPolicy: YAML loading and strict validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.config import PROJECT_ROOT
from src.intelligence.correlation.policy import CorrelationPolicy, load_policy


def test_real_yaml_loads() -> None:
    policy = load_policy(PROJECT_ROOT / "configs" / "correlation_intelligence.yaml")
    assert policy.features.source == "process_sensor"
    assert policy.profiles.global_fallback is False
    assert 0.0 <= policy.thresholds.strong_threshold <= 1.0
    assert policy.shift.enabled is True


def test_defaults_populate_from_empty_mapping() -> None:
    policy = CorrelationPolicy.model_validate({})
    assert policy.thresholds.min_valid_observations == 200
    assert policy.thresholds.redundancy_threshold == 0.95
    assert policy.profiles.exclude_profiles == ["unknown"]


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        CorrelationPolicy.model_validate({"thresholds": {"strong_treshold": 0.8}})


def test_threshold_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        CorrelationPolicy.model_validate({"thresholds": {"strong_threshold": 1.5}})


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "absent.yaml")
