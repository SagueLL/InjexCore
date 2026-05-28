"""Stage 5 — generic temporal features (lag, pct_change, velocity)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.time_series import temporal_features

_SENSOR = "granulator_power"
_SETPOINT = "granulator_power_sp"
_STATE = "granulator_g2_running"


def _indexed(tiny_frame_factory, n: int = 20) -> pd.DataFrame:
    return tiny_frame_factory(n_rows=n, period_s=60.0).set_index("timestamp")


def test_lag_matches_shift(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    df[_SENSOR] = np.arange(20, dtype=float)
    findings = temporal_features.detect(df, ts_policy, groups)
    out = temporal_features.apply(df, findings, ts_policy, groups)
    assert (out[f"{_SENSOR}_lag_1"].dropna() == df[_SENSOR].shift(1).dropna()).all()


def test_velocity_matches_diff(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    df[_SENSOR] = np.arange(20, dtype=float) ** 2
    findings = temporal_features.detect(df, ts_policy, groups)
    out = temporal_features.apply(df, findings, ts_policy, groups)
    assert (
        out[f"{_SENSOR}_velocity_1"].dropna() == df[_SENSOR].diff(1).dropna()
    ).all()


def test_pct_change_matches_pandas(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    df[_SENSOR] = np.arange(1, 21, dtype=float)
    findings = temporal_features.detect(df, ts_policy, groups)
    out = temporal_features.apply(df, findings, ts_policy, groups)
    assert np.allclose(
        out[f"{_SENSOR}_pctchg_1"].dropna(),
        df[_SENSOR].pct_change(1).dropna(),
    )


def test_setpoint_only_emits_lag(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = temporal_features.detect(df, ts_policy, groups)
    sp = [f for f in findings if f.column == _SETPOINT]
    assert sp, "setpoint should have at least the lag feature emitted"
    assert all(f.finding_type == "lag" for f in sp)


def test_state_flag_is_skipped(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = temporal_features.detect(df, ts_policy, groups)
    assert not any(f.column == _STATE for f in findings)
