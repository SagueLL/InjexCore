"""Flatline rule: dynamic thresholds + mixed-profile re-segmentation."""

from __future__ import annotations

import numpy as np
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import rule_flatline


def _policy(**flatline: object) -> SensorHealthPolicy:
    return SensorHealthPolicy.model_validate({"rules": {"flatline": flatline}})


def test_long_constant_run_fires_short_does_not(ctx_factory) -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(50, 5, 200)
    x[100:140] = 42.0  # 40-row constant run in VALIDATION (train = first 100)
    ctx, _ = ctx_factory(x, policy=_policy(min_run_rows=20), train_rows=100)
    result = rule_flatline(ctx)
    assert result.mask[100:140].all()
    assert not result.mask[:100].any()
    short = rng.normal(50, 5, 200)
    short[100:110] = 42.0  # 10 rows < threshold
    ctx, _ = ctx_factory(short, policy=_policy(min_run_rows=20), train_rows=100)
    assert not rule_flatline(ctx).mask.any()


def test_dynamic_threshold_from_train_max_run(ctx_factory) -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(50, 5, 400)
    x[50:90] = 7.0  # train already shows a 40-row constant run
    x[300:355] = 9.0  # validation run of 55 rows < 1.5 x 40 = 60
    ctx, refs = ctx_factory(x, policy=_policy(min_run_rows=20), train_rows=200)
    assert refs.train_max_constant_run["s1"] == 40
    assert not rule_flatline(ctx).mask[300:355].any()
    x[300:370] = 9.0  # 70 rows >= 60 -> fires
    ctx, _ = ctx_factory(x, policy=_policy(min_run_rows=20), train_rows=200)
    assert rule_flatline(ctx).mask[300:370].all()


def test_mixed_profile_run_resegmented(ctx_factory) -> None:
    # One 45-row constant run spanning stopped(30) + run(15); stopped rows are
    # suppressed and the surviving 15-row segment must clear the threshold on
    # its own.
    x = np.r_[np.random.default_rng(3).normal(50, 5, 55), np.full(45, 33.0)]
    profiles = ["run"] * 55 + ["stopped"] * 30 + ["run"] * 15
    ctx, _ = ctx_factory(
        x, profiles=profiles, policy=_policy(min_run_rows=20), train_rows=55
    )
    assert not rule_flatline(ctx).mask.any()  # 15 surviving rows < 20
    ctx, _ = ctx_factory(
        x, profiles=profiles, policy=_policy(min_run_rows=10), train_rows=55
    )
    result = rule_flatline(ctx)
    assert result.mask[85:].all()  # only the surviving run-profile segment
    assert not result.mask[55:85].any()  # stopped rows stay suppressed


def test_zero_runs_left_to_flatline_zero(ctx_factory) -> None:
    x = np.r_[np.random.default_rng(4).normal(50, 5, 100), np.zeros(50)]
    profiles = ["run"] * 150
    ctx, _ = ctx_factory(x, profiles=profiles, policy=_policy(min_run_rows=10))
    assert not rule_flatline(ctx).mask[100:].any()


def test_eps_tolerance_groups_near_equal_values(ctx_factory) -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(50, 5, 120)
    x[60:100] = 42.0 + rng.normal(0, 1e-9, 40)  # jitter below eps
    ctx, _ = ctx_factory(x, policy=_policy(min_run_rows=20, eps=1e-6), train_rows=60)
    assert rule_flatline(ctx).mask[60:100].all()
