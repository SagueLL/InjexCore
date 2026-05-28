"""Unit tests for ``src.data.cleaning.state_consistency``."""
from __future__ import annotations

from typing import Callable

import pandas as pd
import pytest

from src.data.cleaning import state_consistency
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=20)
    assert state_consistency.detect(df, policy, groups) == []


def test_off_with_production_flagged(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[5, "granulator_g2_running"] = 0
    df.loc[5, "granulator_production_rate"] = 5.0
    findings = state_consistency.detect(df, policy, groups)
    target = [f for f in findings if f.finding_type == "off_with_production"]
    assert len(target) == 1
    assert target[0].severity.value == "important"
    assert target[0].action_taken == "tag_only"


def test_on_with_low_power_flagged(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[2, "granulator_g2_running"] = 1
    df.loc[2, "granulator_power"] = 0.0  # < min_power_pct (1.0)
    findings = state_consistency.detect(df, policy, groups)
    target = [f for f in findings if f.finding_type == "on_with_low_power"]
    assert len(target) == 1
    assert target[0].severity.value == "important"


def test_alarm_off_but_hot_flagged(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    # All alarms already 0; bump a temperature above the hot threshold (200°C)
    # but still inside the physical bound [-20, 350].
    df.loc[4, "conditioner_inlet_temp"] = 250.0
    findings = state_consistency.detect(df, policy, groups)
    target = [f for f in findings if f.finding_type == "alarm_off_but_hot"]
    assert len(target) == 1


def test_alarm_persistent_run_flagged_after_window(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # alarm_shutdown_window_min = 10 by default → need > 10 rows with running=0.
    df = tiny_frame_factory(n_rows=20)
    df.loc[2:14, "granulator_g2_alarm"] = 1
    df.loc[2:14, "granulator_g2_running"] = 0
    findings = state_consistency.detect(df, policy, groups)
    target = [
        f for f in findings
        if f.finding_type == "alarm_with_extended_shutdown"
        and f.column == "granulator_g2_alarm"
    ]
    assert len(target) == 1
    assert target[0].severity.value == "aware"


def test_sp_pv_drift_flagged_over_threshold_and_duration(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # sp_pv_max_drift_pct=20 %, sp_pv_drift_min_minutes=30
    df = tiny_frame_factory(n_rows=40)
    # Setpoint at 100, PV at 50 → |SP-PV|/|SP| = 50% > 20% for 40 rows > 30.
    df["conditioner_temp_sp"] = 100.0
    df["conditioner_inlet_temp"] = 50.0
    findings = state_consistency.detect(df, policy, groups)
    drift = [f for f in findings if f.finding_type == "sp_pv_drift"]
    assert len(drift) >= 1
    assert drift[0].severity.value == "aware"


def test_apply_is_noop(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=5)
    df.loc[2, "granulator_g2_running"] = 0
    df.loc[2, "granulator_production_rate"] = 5.0
    findings = state_consistency.detect(df, policy, groups)
    cleaned = state_consistency.apply(df, findings, policy, groups)
    pd.testing.assert_frame_equal(cleaned, df)
