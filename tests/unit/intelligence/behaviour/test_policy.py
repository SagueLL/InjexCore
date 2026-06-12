"""Behaviour Intelligence — policy loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.intelligence.behaviour.policy import BehaviourPolicy, load_policy


def test_real_yaml_loads(behaviour_policy: BehaviourPolicy) -> None:
    assert behaviour_policy.fit_window.strategy == "fraction"
    assert behaviour_policy.profiles.enabled is True
    assert "cleaning" in behaviour_policy.profiles.unsupported_regimes


def test_defaults_populate() -> None:
    p = BehaviourPolicy.model_validate({})
    assert p.fit_window.train_fraction == 0.7
    assert p.sensors.source == "process_sensor"
    assert p.profiles.production_quantiles == [0.33, 0.67]
    assert p.baselines.percentiles == [5, 25, 50, 75, 95]


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        BehaviourPolicy.model_validate({"sensors": {"sorce": "process_sensor"}})


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        BehaviourPolicy.model_validate({"correlations": {"enabled": True}})


def test_train_fraction_range_validated() -> None:
    with pytest.raises(ValidationError):
        BehaviourPolicy.model_validate({"fit_window": {"train_fraction": 1.5}})


def test_bad_strategy_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        BehaviourPolicy.model_validate({"fit_window": {"strategy": "rolling"}})


def test_bad_sensor_source_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        BehaviourPolicy.model_validate({"sensors": {"source": "all_columns"}})


def test_missing_policy_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "does_not_exist.yaml")
