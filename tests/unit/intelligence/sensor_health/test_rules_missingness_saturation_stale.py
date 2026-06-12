"""Missingness spike, saturation and stale-signal rules."""

from __future__ import annotations

import numpy as np
from src.intelligence.sensor_health.policy import SensorHealthPolicy
from src.intelligence.sensor_health.rules import (
    rule_flatline,
    rule_flatline_zero,
    rule_missingness_spike,
    rule_saturation,
    rule_stale_signal,
)


def _policy(**rules: dict) -> SensorHealthPolicy:
    return SensorHealthPolicy.model_validate({"rules": rules})


def test_new_outage_on_clean_sensor_fires(ctx_factory) -> None:
    rng = np.random.default_rng(1)
    x = np.r_[rng.normal(50, 5, 400), np.full(300, np.nan)]
    policy = _policy(missingness_spike={"window_rows": 120})
    ctx, _ = ctx_factory(x, policy=policy, train_rows=400)
    result = rule_missingness_spike(ctx)
    assert result.mask[520:].any()
    assert not result.mask[:400].any()


def test_chronic_missingness_never_spikes(ctx_factory) -> None:
    # Train already contains full outage blocks (rolling fraction 1.0): the
    # threshold self-raises above 1 and validation outages cannot fire.
    rng = np.random.default_rng(2)
    x = rng.normal(50, 5, 800)
    x[100:300] = np.nan  # train outage longer than the window
    x[600:800] = np.nan  # validation outage with the same pattern
    policy = _policy(missingness_spike={"window_rows": 120})
    ctx, refs = ctx_factory(x, policy=policy, train_rows=400)
    assert refs.train_max_rolling_nan_fraction["s1"] == 1.0
    assert not rule_missingness_spike(ctx).mask.any()


def test_saturation_requires_configured_bounds(ctx_factory) -> None:
    x = np.r_[np.random.default_rng(3).normal(50, 5, 100), np.full(60, 100.0)]
    ctx, _ = ctx_factory(x)  # no physical bounds in metadata
    assert rule_saturation(ctx, np.zeros(len(x), dtype=bool)) == []
    policy = SensorHealthPolicy.model_validate(
        {"sensors": {"overrides": {"s1": {"physical_max": 100.0}}}}
    )
    ctx, _ = ctx_factory(x, policy=policy)
    results = rule_saturation(ctx, np.zeros(len(x), dtype=bool))
    high = next(r for r in results if r.issue_type == "saturation_high")
    assert high.mask[100:].all()


def test_saturation_low_defers_zero_runs_to_flatline_zero(ctx_factory) -> None:
    x = np.r_[np.random.default_rng(4).normal(50, 5, 100), np.zeros(60)]
    policy = SensorHealthPolicy.model_validate(
        {"sensors": {"overrides": {"s1": {"physical_min": 0.0}}}}
    )
    ctx, _ = ctx_factory(x, policy=policy, train_rows=100)
    fz = rule_flatline_zero(ctx)
    low = next(
        r for r in rule_saturation(ctx, fz.mask) if r.issue_type == "saturation_low"
    )
    assert fz.mask[100:].all()
    assert not low.mask.any()  # the zero run is owned by flatline_zero


def test_stale_fires_only_below_train_minimum(ctx_factory) -> None:
    rng = np.random.default_rng(5)
    x = np.r_[
        rng.normal(50, 5, 400),  # train: rich values
        np.repeat(rng.normal(50, 5, 4), 50),  # validation: 4 values / 200 rows
    ]
    policy = _policy(stale_signal={"window_rows": 60, "max_unique_fraction": 0.2})
    ctx, _ = ctx_factory(x, policy=policy, train_rows=400)
    flat = rule_flatline(ctx)
    result = rule_stale_signal(ctx, flat.mask)
    assert result.mask[480:].any()
    assert not result.mask[:400].any()  # never contradicts its own reference


def test_stale_inert_when_train_is_already_stale(ctx_factory) -> None:
    rng = np.random.default_rng(6)
    x = np.repeat(rng.normal(50, 5, 12), 50)  # quantized everywhere
    policy = _policy(stale_signal={"window_rows": 60, "max_unique_fraction": 0.2})
    ctx, _ = ctx_factory(x, policy=policy, train_rows=300)
    flat = rule_flatline(ctx)
    assert not rule_stale_signal(ctx, flat.mask).mask.any()
