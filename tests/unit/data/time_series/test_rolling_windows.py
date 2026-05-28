"""Stage 4 — rolling-window features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.time_series import rolling_windows
from src.data.time_series.policy import TimeSeriesPolicy

_SENSOR = "granulator_power"
_SETPOINT = "granulator_power_sp"
_STATE = "granulator_g2_running"
_ALARM = "granulator_g2_alarm"


def _indexed(tiny_frame_factory, n: int = 20) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_process_sensor_emits_all_three_families(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = rolling_windows.detect(df, ts_policy, groups)
    for family in ("rolling_mean", "rolling_std", "rolling_trend"):
        assert any(f.column == _SENSOR and f.finding_type == family for f in findings)


def test_setpoint_emits_no_rolling(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = rolling_windows.detect(df, ts_policy, groups)
    assert not any(f.column == _SETPOINT for f in findings)


def test_state_and_alarm_are_skipped(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory)
    findings = rolling_windows.detect(df, ts_policy, groups)
    assert not any(f.column == _STATE for f in findings)
    assert not any(f.column == _ALARM for f in findings)


def test_closed_left_is_leak_safe(tiny_frame_factory, ts_policy, groups):
    df = _indexed(tiny_frame_factory, n=20)
    df[_SENSOR] = np.arange(20, dtype=float)  # 0, 1, 2, ... 19

    findings = rolling_windows.detect(df, ts_policy, groups)
    out = rolling_windows.apply(df, findings, ts_policy, groups)

    # Mean over the previous 5 samples at row 10 must equal mean(5..9) = 7,
    # NOT mean(6..10) = 8 (which would leak the current value).
    col = f"{_SENSOR}_mean_5"
    assert col in out.columns
    expected = df[_SENSOR].iloc[5:10].mean()
    assert out[col].iloc[10] == expected
    # Row 0 has no history → NaN.
    assert pd.isna(out[col].iloc[0])


def test_override_widens_windows():
    """Override on granulator_production_rate adds the [240] window."""
    policy = TimeSeriesPolicy.model_validate(
        {
            "category_defaults": {
                "process_sensor": {
                    "rolling_mean": {"enabled": True, "windows": [5, 15, 60]},
                },
            },
            "overrides": {
                "granulator_production_rate": {"windows": [5, 15, 60, 240]},
            },
        }
    )
    spec = policy.resolve("process_sensor", "granulator_production_rate")
    assert spec.rolling_mean.windows == [5, 15, 60, 240]


def test_disable_families_via_override():
    policy = TimeSeriesPolicy.model_validate(
        {
            "category_defaults": {
                "process_sensor": {
                    "pct_change": {"enabled": True, "lags": [1]},
                    "velocity": {"enabled": True, "lags": [1]},
                },
            },
            "overrides": {
                "inlet_hopper_points": {"disable_families": ["pct_change", "velocity"]},
            },
        }
    )
    spec = policy.resolve("process_sensor", "inlet_hopper_points")
    assert spec.pct_change.enabled is False
    assert spec.velocity.enabled is False
