"""Family 1 — temporal derivatives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data.feature_engineering import temporal_derivatives
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


_SENSOR = "granulator_power"


def _indexed(tiny_frame_factory, n: int = 30) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_acceleration_findings_emitted(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = temporal_derivatives.detect(df, fe_policy, groups)
    accel = [f for f in findings if f.finding_type == "acceleration" and f.column == _SENSOR]
    assert len(accel) == len(fe_policy.temporal_derivatives.acceleration.lags)


def test_acceleration_matches_diff_diff(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df[_SENSOR] = np.arange(len(df), dtype=float) ** 2  # 0,1,4,9,...

    findings = temporal_derivatives.detect(df, fe_policy, groups)
    out = temporal_derivatives.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_accel_1"
    assert col in out.columns
    expected = df[_SENSOR].diff(1).diff(1)
    pd.testing.assert_series_equal(
        out[col].rename(_SENSOR), expected, check_names=False,
    )


def test_sign_change_rate_counts_oscillation(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df[_SENSOR] = np.tile([1.0, 2.0], len(df) // 2 + 1)[: len(df)]

    findings = temporal_derivatives.detect(df, fe_policy, groups)
    out = temporal_derivatives.apply(df, findings, fe_policy, groups)

    col = f"{_SENSOR}_signchanges_15"
    assert col in out.columns
    # After the warm-up region the rolling window of 15 samples on a
    # strict ±1 alternation should contain ~14 sign flips.
    assert out[col].iloc[20] >= 10


def test_sp_pv_deviation_is_emitted(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    df["granulator_power"] = 55.0
    df["granulator_power_sp"] = 50.0

    findings = temporal_derivatives.detect(df, fe_policy, groups)
    out = temporal_derivatives.apply(df, findings, fe_policy, groups)

    col = "granulator_power_minus_granulator_power_sp"
    assert col in out.columns
    assert (out[col] == 5.0).all()


def test_sp_pv_missing_yields_important_finding(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory).drop(columns=["granulator_power_sp"])
    findings = temporal_derivatives.detect(df, fe_policy, groups)
    assert any(
        f.finding_type == "sp_pv_deviation_missing"
        and f.severity.value == "important"
        for f in findings
    )


def test_disabled_family_skips_everything(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {"temporal_derivatives": {"enabled": False}}
    )
    df = _indexed(tiny_frame_factory)
    findings = temporal_derivatives.detect(df, policy, groups)
    assert len(findings) == 1
    assert findings[0].finding_type == "skipped"

    out = temporal_derivatives.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)


def test_setpoints_and_states_not_targeted(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = temporal_derivatives.detect(df, fe_policy, groups)
    accel_cols = {f.column for f in findings if f.finding_type == "acceleration"}
    assert "granulator_power_sp" not in accel_cols
    assert "granulator_g2_running" not in accel_cols
    assert "granulator_g2_alarm" not in accel_cols
