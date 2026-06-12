"""PcaPolicy: YAML loading and strict validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.config import PROJECT_ROOT
from src.intelligence.pca.policy import PcaPolicy, load_policy


def test_real_yaml_loads() -> None:
    policy = load_policy(PROJECT_ROOT / "configs" / "pca_intelligence.yaml")
    assert policy.model.explained_variance_target == 0.95
    assert policy.model.scaler == "robust"
    assert policy.model.missing_policy == "median_impute"
    assert policy.profiles.global_fallback is False


def test_defaults_populate_from_empty_mapping() -> None:
    policy = PcaPolicy.model_validate({})
    assert policy.model.min_features == 3
    assert policy.model.random_state == 42
    assert policy.model.max_components is None


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        PcaPolicy.model_validate({"model": {"explaned_variance_target": 0.9}})


def test_invalid_scaler_rejected() -> None:
    with pytest.raises(ValidationError):
        PcaPolicy.model_validate({"model": {"scaler": "minmax"}})


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "absent.yaml")
