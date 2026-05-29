"""Family 5 — operative features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.feature_engineering import operative_features
from src.data.feature_engineering.policy import FeatureEngineeringPolicy


def _indexed(tiny_frame_factory, n: int = 30) -> pd.DataFrame:
    df = tiny_frame_factory(n_rows=n, period_s=60.0)
    return df.set_index("timestamp")


def test_time_since_machine_off_resets_on_rising_edge(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=10)
    # All running flags off for 5 samples, then on.
    for c in ("granulator_g2_running", "feeder_al2_running", "conditioner_me2_direct"):
        df[c] = [0.0] * 5 + [1.0] * 5

    findings = operative_features.detect(df, fe_policy, groups)
    out = operative_features.apply(df, findings, fe_policy, groups)

    col = "time_since_machine_off"
    assert col in out.columns
    # Before any activation → NaN.
    assert pd.isna(out[col].iloc[0])
    # At index 5 the OR(running) goes 0→1 → counter resets to 0.
    assert out[col].iloc[5] == 0.0
    assert out[col].iloc[6] == 1.0


def test_n_subsystems_running_sums_flags(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=4)
    df["granulator_g2_running"] = [1.0, 1.0, 0.0, 1.0]
    df["feeder_al2_running"] = [1.0, 0.0, 0.0, 1.0]
    df["conditioner_me2_direct"] = [0.0, 0.0, 0.0, 1.0]

    findings = operative_features.detect(df, fe_policy, groups)
    out = operative_features.apply(df, findings, fe_policy, groups)

    col = "n_subsystems_running"
    assert col in out.columns
    assert list(out[col]) == [2.0, 1.0, 0.0, 3.0]


def test_cumulative_starts_counts_rising_edges(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=8)
    # OR sequence: 0,0,1,1,0,1,0,1  → 3 rising edges total
    df["granulator_g2_running"] = [0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    df["feeder_al2_running"] = 0.0
    df["conditioner_me2_direct"] = 0.0

    findings = operative_features.detect(df, fe_policy, groups)
    out = operative_features.apply(df, findings, fe_policy, groups)

    col = "cumulative_starts"
    assert col in out.columns
    assert out[col].iloc[-1] == 3.0


def test_any_alarm_while_running_is_boolean(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=4)
    df["granulator_g2_running"] = [1.0, 1.0, 0.0, 1.0]
    df["feeder_al2_running"] = 0.0
    df["conditioner_me2_direct"] = 0.0
    df["granulator_g2_alarm"] = [0.0, 1.0, 1.0, 0.0]
    df["feeder_al2_alarm"] = 0.0
    df["conditioner_me2_alarm"] = 0.0

    findings = operative_features.detect(df, fe_policy, groups)
    out = operative_features.apply(df, findings, fe_policy, groups)

    col = "any_alarm_while_running"
    assert col in out.columns
    # Only index 1 has both: alarm AND running.
    assert list(out[col]) == [0, 1, 0, 0]


def test_total_alarms_rolling_window(tiny_frame_factory, fe_policy, groups):
    df = _indexed(tiny_frame_factory, n=80)
    df["granulator_g2_alarm"] = 0.0
    df.loc[df.index[10], "granulator_g2_alarm"] = 1.0
    df.loc[df.index[40], "granulator_g2_alarm"] = 1.0

    findings = operative_features.detect(df, fe_policy, groups)
    out = operative_features.apply(df, findings, fe_policy, groups)

    col = "total_alarms_60"
    assert col in out.columns
    # By the end of the record both edges fall outside the 60-sample window.
    # Mid-window at index 50 must see at least the second edge.
    assert out[col].iloc[50] >= 1.0


def test_disabled_returns_skipped(tiny_frame_factory, groups):
    policy = FeatureEngineeringPolicy.model_validate(
        {"operative_features": {"enabled": False}}
    )
    df = _indexed(tiny_frame_factory)
    findings = operative_features.detect(df, policy, groups)
    assert findings[0].finding_type == "skipped"

    out = operative_features.apply(df, findings, policy, groups)
    assert list(out.columns) == list(df.columns)
