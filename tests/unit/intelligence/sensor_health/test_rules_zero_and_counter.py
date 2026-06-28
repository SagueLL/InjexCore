"""flatline_zero suppression semantics + counter_reset sub-states."""

from __future__ import annotations

import numpy as np
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import (
    rule_counter_reset,
    rule_flatline_zero,
)


def test_zero_is_abnormal_sensor_fires_at_lower_threshold(ctx_factory) -> None:
    rng = np.random.default_rng(1)
    x = np.r_[rng.normal(50, 5, 200), np.zeros(20)]  # never zero in train
    ctx, _ = ctx_factory(x, train_rows=200)
    result = rule_flatline_zero(ctx)
    assert result.detail["zero_is_abnormal"] is True
    assert result.detail["threshold_rows"] == 15
    assert result.mask[200:].all()
    x10 = np.r_[rng.normal(50, 5, 200), np.zeros(10)]  # below 15-row threshold
    ctx, _ = ctx_factory(x10, train_rows=200)
    assert not rule_flatline_zero(ctx).mask.any()


def test_allowed_profile_zeros_fully_suppressed(ctx_factory) -> None:
    rng = np.random.default_rng(2)
    x = np.r_[rng.normal(50, 5, 100), np.zeros(200)]
    profiles = ["run"] * 100 + ["stopped"] * 200
    policy = SensorHealthPolicy.model_validate(
        {
            "sensors": {
                "overrides": {"s1": {"expected_zero_during_profiles": ["stopped"]}}
            }
        }
    )
    ctx, _ = ctx_factory(x, profiles=profiles, policy=policy)
    assert not rule_flatline_zero(ctx).mask.any()


def test_all_profile_allowed_sensor_is_inert(ctx_factory) -> None:
    # steam_valve_flow_me2-style: zero normal in every profile.
    x = np.r_[np.random.default_rng(3).normal(50, 5, 50), np.zeros(300)]
    policy = SensorHealthPolicy.model_validate(
        {"sensors": {"overrides": {"s1": {"expected_zero_during_profiles": ["run"]}}}}
    )
    ctx, _ = ctx_factory(x, policy=policy)
    assert not rule_flatline_zero(ctx).mask.any()


def _counter_policy(**counter: object) -> SensorHealthPolicy:
    base = {
        "drop_fraction": 0.9,
        "low_ceiling_fraction": 0.01,
        "detect_window_rows": 5,
        "recovery_window_rows": 20,
        "persistent_zero_rows": 60,
    }
    base.update(counter)
    return SensorHealthPolicy.model_validate(
        {
            "rules": {"counter_reset": base},
            "sensors": {"overrides": {"s1": {"kind": "counter"}}},
        }
    )


def test_oscillation_does_not_trigger(ctx_factory) -> None:
    rng = np.random.default_rng(4)
    x = 800_000 + rng.normal(0, 30_000, 300)  # oscillating, non-monotone
    ctx, _ = ctx_factory(x, policy=_counter_policy())
    assert not rule_counter_reset(ctx).mask.any()


def test_persistent_zero_after_reset(ctx_factory) -> None:
    rng = np.random.default_rng(5)
    x = np.r_[800_000 + rng.normal(0, 10_000, 200), np.zeros(100)]
    ctx, _ = ctx_factory(x, policy=_counter_policy(), train_rows=200)
    result = rule_counter_reset(ctx)
    assert result.mask[200:].all()
    assert set(result.substates[200:]) == {"persistent_zero_after_reset"}


def test_recovered_after_reset_is_weak(ctx_factory) -> None:
    rng = np.random.default_rng(6)
    x = np.r_[
        800_000 + rng.normal(0, 10_000, 200),
        np.zeros(10),
        800_000 + rng.normal(0, 10_000, 90),
    ]
    ctx, _ = ctx_factory(x, policy=_counter_policy(), train_rows=200)
    result = rule_counter_reset(ctx)
    assert set(result.substates[200:210]) == {"recovered_after_reset"}
    assert result.strength[205] == 0.5


def test_reset_to_zero_vs_reset_detected(ctx_factory) -> None:
    rng = np.random.default_rng(7)
    base = 800_000 + rng.normal(0, 10_000, 200)
    to_zero = np.r_[base, np.zeros(40)]
    ctx, _ = ctx_factory(to_zero, policy=_counter_policy(), train_rows=200)
    assert set(rule_counter_reset(ctx).substates[200:]) == {"reset_to_zero"}
    low_not_zero = np.r_[base, np.full(40, 500.0)]  # below ceiling, not zero
    ctx, _ = ctx_factory(low_not_zero, policy=_counter_policy(), train_rows=200)
    assert set(rule_counter_reset(ctx).substates[200:]) == {"reset_detected"}


def test_non_counter_sensor_returns_none(ctx_factory) -> None:
    ctx, _ = ctx_factory(np.zeros(50) + 5.0)
    assert rule_counter_reset(ctx) is None
