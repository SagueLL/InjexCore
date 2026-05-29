"""Feature engineering policy schema."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.data.feature_engineering.policy import (
    FeatureEngineeringPolicy,
    RatioSpec,
)


def test_defaults_are_consistent(fe_policy: FeatureEngineeringPolicy):
    assert fe_policy.temporal_derivatives.enabled is True
    assert fe_policy.stability.enabled is True
    assert fe_policy.physical_ratios.enabled is True
    assert fe_policy.energetic_features.enabled is True
    assert fe_policy.operative_features.enabled is True
    assert fe_policy.anomaly_features.enabled is True
    # Global z is OFF by default (leakage).
    assert fe_policy.anomaly_features.global_z.enabled is False
    # Per-cycle is OFF until a cycle marker exists.
    assert fe_policy.energetic_features.per_cycle.enabled is False


def test_unknown_keys_are_rejected():
    with pytest.raises(ValidationError):
        FeatureEngineeringPolicy.model_validate({"not_a_real_section": {}})


def test_sp_pv_pairs_load_as_mapping(fe_policy: FeatureEngineeringPolicy):
    pairs = fe_policy.temporal_derivatives.sp_pv_deviation.pairs
    assert pairs["granulator_power_sp"] == "granulator_power"
    assert pairs["conditioner_temp_sp"] == "conditioner_steam_loop_temp"


def test_ratio_spec_requires_b_for_diff():
    spec = RatioSpec(name="x", op="diff", a="a", b="b")
    assert spec.b == "b"


def test_ratio_spec_scale_keeps_factor():
    spec = RatioSpec(name="x", op="scale", a="a", factor=0.001)
    assert spec.factor == 0.001
