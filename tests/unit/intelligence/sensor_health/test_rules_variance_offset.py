"""Variance collapse/explosion + abrupt offset (per-profile referenced)."""

from __future__ import annotations

import numpy as np
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import (
    rule_abrupt_offset,
    rule_variance_collapse,
    rule_variance_explosion,
)


def _policy(**rules: dict) -> SensorHealthPolicy:
    return SensorHealthPolicy.model_validate({"rules": rules})


def test_collapse_fires_only_below_train_minimum(ctx_factory) -> None:
    rng = np.random.default_rng(1)
    x = np.r_[rng.normal(50, 5, 300), 50 + rng.normal(0, 1e-4, 100)]
    ctx, refs = ctx_factory(x, train_rows=300)
    result = rule_variance_collapse(ctx)
    assert result.mask[370:].any()  # collapsed window fully inside the flat part
    assert not result.mask[:300].any()  # never contradicts its own reference


def test_normal_variance_does_not_fire(ctx_factory) -> None:
    x = np.random.default_rng(2).normal(50, 5, 400)
    ctx, _ = ctx_factory(x, train_rows=300)
    assert not rule_variance_collapse(ctx).mask.any()


def test_purity_guard_suppresses_profile_transitions(ctx_factory) -> None:
    rng = np.random.default_rng(3)
    x = np.r_[rng.normal(50, 5, 300), 50 + rng.normal(0, 1e-4, 100)]
    profiles = ["run"] * 350 + ["other"] * 50  # change inside the flat block
    ctx, _ = ctx_factory(x, profiles=profiles, train_rows=300)
    result = rule_variance_collapse(ctx)
    window = ctx.policy.rules.variance_collapse.window_rows
    assert not result.mask[350 : 350 + window - 1].any()  # impure windows


def test_explosion_fires_on_sudden_noise(ctx_factory) -> None:
    rng = np.random.default_rng(4)
    x = np.r_[rng.normal(50, 5, 300), rng.normal(50, 200, 100)]
    ctx, _ = ctx_factory(x, train_rows=300)
    assert rule_variance_explosion(ctx).mask[370:].any()
    assert not rule_variance_explosion(ctx).mask[:300].any()


def test_inactive_without_baseline(ctx_factory, baselines_factory) -> None:
    rng = np.random.default_rng(5)
    x = np.r_[rng.normal(50, 5, 300), 50 + rng.normal(0, 1e-4, 100)]
    baselines = baselines_factory(["unrelated_profile"], ["s1"])
    ctx, refs = ctx_factory(x, train_rows=300, baselines=baselines)
    assert not rule_variance_collapse(ctx).mask.any()
    assert any(u["sensor"] == "s1" for u in refs.unsupported)


def test_abrupt_offset_step_fires_warning_capped(ctx_factory) -> None:
    rng = np.random.default_rng(6)
    x = np.r_[rng.normal(50, 5, 300), rng.normal(150, 5, 100)]  # +100 step
    ctx, _ = ctx_factory(x, train_rows=300)
    result = rule_abrupt_offset(ctx)
    assert result.mask[300:340].any()
    assert result.strength.max() <= 0.6  # warning-capped strength


def test_abrupt_offset_suppressed_across_profile_change(ctx_factory) -> None:
    rng = np.random.default_rng(7)
    x = np.r_[rng.normal(50, 5, 300), rng.normal(150, 5, 100)]
    profiles = ["run"] * 300 + ["other"] * 100  # step coincides with profile change
    ctx, _ = ctx_factory(x, profiles=profiles, train_rows=300)
    assert not rule_abrupt_offset(ctx).mask.any()
