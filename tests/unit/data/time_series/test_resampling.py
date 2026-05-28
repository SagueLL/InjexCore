"""Stage 3 — optional resampling behaviour."""
from __future__ import annotations

import pandas as pd

from src.data.time_series import resampling
from src.data.time_series.policy import TimeSeriesPolicy


def test_disabled_is_noop(tiny_frame_factory, ts_policy, groups):
    df = tiny_frame_factory(n_rows=10).set_index("timestamp")
    findings = resampling.detect(df, ts_policy, groups)
    assert any(f.finding_type == "skipped" for f in findings)
    out = resampling.apply(df, findings, ts_policy, groups)
    assert out is df


def test_enabled_aggregates_per_category(tiny_frame_factory, groups):
    # Synthetic 1-second cadence so resample("5s") aggregates groups of 5.
    df = tiny_frame_factory(n_rows=10, period_s=1.0).set_index("timestamp")
    # Make the sensor signal non-constant so the mean is informative.
    df["granulator_power"] = [0.0, 1.0, 2.0, 3.0, 4.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    # Make a running flag flip during the second window.
    df["granulator_g2_running"] = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]

    policy = TimeSeriesPolicy.model_validate(
        {"resampling": {"enabled": True, "rule": "5s"}}
    )
    findings = resampling.detect(df, policy, groups)
    out = resampling.apply(df, findings, policy, groups)

    # process_sensor → mean
    assert out["granulator_power"].iloc[0] == 2.0
    assert out["granulator_power"].iloc[1] == 30.0
    # state_flag → max (any-on in the window)
    assert out["granulator_g2_running"].iloc[1] == 1
