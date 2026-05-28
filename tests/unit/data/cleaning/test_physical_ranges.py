"""Unit tests for ``src.data.cleaning.physical_ranges``."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import pytest

from src.data.cleaning import physical_ranges
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import Bound, CleaningPolicy


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=20)
    assert physical_ranges.detect(df, policy, groups) == []


@pytest.mark.parametrize(
    "column, bad_value",
    [
        ("conditioner_inlet_temp", 999.0),  # critical → mask_nan
        ("steam_valve_pressure_me2", 5000.0),  # critical → mask_nan
        ("inlet_hopper_humidity", 250.0),  # critical → mask_nan
    ],
)
def test_critical_bound_masks_to_nan(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
    column: str,
    bad_value: float,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[4, column] = bad_value
    findings = physical_ranges.detect(df, policy, groups)
    oob = [
        f for f in findings
        if f.finding_type == "out_of_range" and f.column == column
    ]
    assert len(oob) == 1
    assert oob[0].severity.value == "critical"
    assert oob[0].action_taken == "mask_nan"

    cleaned = physical_ranges.apply(df, findings, policy, groups)
    assert pd.isna(cleaned.loc[4, column])


def test_important_bound_with_clip_disabled_masks(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # 'granulator_power' bound = (0, 110, important); clip_soft_violations=False
    df = tiny_frame_factory(n_rows=10)
    df.loc[2, "granulator_power"] = 500.0
    findings = physical_ranges.detect(df, policy, groups)
    oob = [f for f in findings if f.column == "granulator_power"]
    assert len(oob) == 1
    assert oob[0].severity.value == "important"
    assert oob[0].action_taken == "mask_nan"

    cleaned = physical_ranges.apply(df, findings, policy, groups)
    assert pd.isna(cleaned.loc[2, "granulator_power"])


def test_important_bound_with_clip_enabled_clips(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    groups: ColumnGroups,
) -> None:
    # Build a minimal local policy with clip enabled, single bound override.
    policy = CleaningPolicy()
    policy.physical_ranges.clip_soft_violations = True
    policy.physical_ranges.bounds = {
        "granulator_power": Bound(min=0.0, max=110.0, severity="important"),
    }
    df = tiny_frame_factory(n_rows=6)
    df.loc[1, "granulator_power"] = 500.0
    findings = physical_ranges.detect(df, policy, groups)
    assert findings[0].action_taken == "clip"

    cleaned = physical_ranges.apply(df, findings, policy, groups)
    assert cleaned.loc[1, "granulator_power"] == 110.0


def test_integer_column_flags_fractional_values(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # 'granulator_g2_running' bound has integer=true, range [0,1]
    df = tiny_frame_factory(n_rows=10)
    df.loc[3, "granulator_g2_running"] = 0.5  # in range but fractional
    findings = physical_ranges.detect(df, policy, groups)
    frac = [
        f for f in findings
        if f.finding_type == "non_integer_in_integer_column"
        and f.column == "granulator_g2_running"
    ]
    assert len(frac) == 1
    assert frac[0].action_taken == "mask_nan"


def test_empty_frame_returns_no_findings(
    empty_frame: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    assert physical_ranges.detect(empty_frame, policy, groups) == []
