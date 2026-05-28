"""Unit tests for ``src.data.cleaning.missing_values``."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import pytest

from src.data.cleaning import missing_values
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=20)
    assert missing_values.detect(df, policy, groups) == []


def test_undeterminable_state_drops_rows(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[3, "granulator_g2_running"] = np.nan
    findings = missing_values.detect(df, policy, groups)
    undet = [f for f in findings if f.finding_type == "undeterminable_state"]
    assert len(undet) == 1
    assert undet[0].severity.value == "critical"
    assert undet[0].action_taken == "drop"

    cleaned = missing_values.apply(df, findings, policy, groups)
    assert len(cleaned) == 9


def test_machine_off_keeps_nan(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    # Machine off: both granulator_g2_running and feeder_al2_running = 0.
    df.loc[3:5, "granulator_g2_running"] = 0
    df.loc[3:5, "feeder_al2_running"] = 0
    df.loc[3:5, "granulator_roller_gap"] = np.nan
    findings = missing_values.detect(df, policy, groups)
    target = [
        f for f in findings
        if f.column == "granulator_roller_gap"
        and f.finding_type == "machine_off"
    ]
    assert len(target) == 1
    assert target[0].severity.value == "aware"
    assert target[0].action_taken == "keep_nan"

    cleaned = missing_values.apply(df, findings, policy, groups)
    # Row indices shift only if undeterminable rows are dropped; none here.
    assert pd.isna(cleaned.loc[3, "granulator_roller_gap"])
    assert pd.isna(cleaned.loc[5, "granulator_roller_gap"])


def test_broken_sensor_long_run_critical(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # broken_sensor_min_run = 30 by default; need NaN run > 30 with running.
    df = tiny_frame_factory(n_rows=40)
    df.loc[5:38, "granulator_roller_gap"] = np.nan
    findings = missing_values.detect(df, policy, groups)
    target = [
        f for f in findings
        if f.column == "granulator_roller_gap"
        and f.finding_type == "broken_sensor"
    ]
    assert len(target) == 1
    assert target[0].severity.value == "critical"


def test_lost_communication_short_run_interpolates(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # interpolation_max_run = 5; run of 3 NaNs with running flags=1.
    df = tiny_frame_factory(n_rows=10)
    df["granulator_roller_gap"] = [float(i + 1) for i in range(10)]
    df.loc[4:6, "granulator_roller_gap"] = np.nan
    findings = missing_values.detect(df, policy, groups)
    target = [
        f for f in findings
        if f.column == "granulator_roller_gap"
        and f.finding_type == "lost_communication"
    ]
    assert len(target) == 1
    assert target[0].severity.value == "important"
    assert target[0].action_taken == "interpolate_time"

    cleaned = missing_values.apply(df, findings, policy, groups)
    # After time interpolation, the NaN cells are filled with intermediate values.
    assert cleaned["granulator_roller_gap"].iloc[4:7].notna().all()


def test_missing_by_design_kept_as_nan(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # batch_id is metadata of object dtype; cast to object first.
    df = tiny_frame_factory(n_rows=10)
    df["batch_id"] = df["batch_id"].astype(object)
    df.loc[2:4, "batch_id"] = np.nan
    findings = missing_values.detect(df, policy, groups)
    target = [
        f for f in findings
        if f.column == "batch_id" and f.finding_type == "missing_by_design"
    ]
    assert len(target) == 1
    assert target[0].severity.value == "normal"
    assert target[0].action_taken == "keep_nan"


def test_empty_frame_returns_no_findings(
    empty_frame: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    assert missing_values.detect(empty_frame, policy, groups) == []
