"""AnomalyPolicy: YAML loading and strict validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.config import PROJECT_ROOT
from src.intelligence.anomaly.policy import AnomalyPolicy, load_policy


def test_real_yaml_loads() -> None:
    policy = load_policy(PROJECT_ROOT / "configs" / "anomaly_intelligence.yaml")
    assert policy.combine.method == "max"
    assert policy.isolation_forest.random_state == 42
    assert policy.mahalanobis.estimator == "ledoit_wolf"
    assert policy.statistical.lower_percentile == "p05"
    assert policy.combine.anomaly_percentile > policy.combine.warning_percentile


def test_defaults_populate_from_empty_mapping() -> None:
    policy = AnomalyPolicy.model_validate({})
    assert policy.statistical.robust_z_threshold == 3.5
    assert policy.pca_detector.q_threshold_percentile == 99.0
    assert set(policy.combine.weights) == {
        "statistical",
        "mahalanobis",
        "pca_q",
        "pca_t2",
        "isolation_forest",
    }


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        AnomalyPolicy.model_validate({"isolation_forest": {"n_stimators": 100}})


def test_invalid_combine_method_rejected() -> None:
    with pytest.raises(ValidationError):
        AnomalyPolicy.model_validate({"combine": {"method": "median"}})


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "absent.yaml")
