"""Unit tests for ``src.data.cleaning.frozen_sensors``."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import pytest

from src.data.cleaning import frozen_sensors
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy, FrozenSensorsPolicy


def _short_policy(base: CleaningPolicy, min_minutes: int = 5) -> CleaningPolicy:
    """Clone the real policy with a shorter frozen_min_minutes for tests."""
    new = base.model_copy(deep=True)
    new.frozen_sensors = FrozenSensorsPolicy(
        frozen_min_minutes=min_minutes,
        epsilon_rate_cols=base.frozen_sensors.epsilon_rate_cols,
        epsilon=base.frozen_sensors.epsilon,
        skip_columns=base.frozen_sensors.skip_columns,
    )
    return new


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    # Vary process cols so nothing looks frozen.
    for i, col in enumerate(groups.process):
        df[col] = [float(j + i) for j in range(len(df))]
    assert frozen_sensors.detect(df, policy, groups) == []


def test_frozen_process_column_flagged_important(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    short_policy = _short_policy(policy, min_minutes=5)
    df = tiny_frame_factory(n_rows=10)
    # Vary other process cols so only 'granulator_roller_gap' looks frozen.
    for col in groups.process:
        if col != "granulator_roller_gap":
            df[col] = [float(j) for j in range(len(df))]
    # 'granulator_roller_gap' constant at 3.0 for 10 samples, running flags on.
    df["granulator_roller_gap"] = 3.0
    findings = frozen_sensors.detect(df, short_policy, groups)
    target = [f for f in findings if f.column == "granulator_roller_gap"]
    assert len(target) == 1
    assert target[0].finding_type == "frozen_run"
    # Running flags on → not 'aware'; not a forecasting target → 'important'.
    assert target[0].severity.value == "important"
    assert target[0].action_taken == "tag_only"


def test_frozen_forecasting_target_is_critical_and_masked(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    short_policy = _short_policy(policy, min_minutes=5)
    df = tiny_frame_factory(n_rows=10)
    # Vary other process cols.
    for col in groups.process:
        if col != "conditioner_steam_loop_temp":
            df[col] = [float(j) for j in range(len(df))]
    # 'conditioner_steam_loop_temp' is a temperature_forecasting target.
    df["conditioner_steam_loop_temp"] = 80.0
    findings = frozen_sensors.detect(df, short_policy, groups)
    target = [f for f in findings if f.column == "conditioner_steam_loop_temp"]
    assert len(target) == 1
    assert target[0].severity.value == "critical"
    assert target[0].action_taken == "mask_nan"

    cleaned = frozen_sensors.apply(df, findings, short_policy, groups)
    assert cleaned["conditioner_steam_loop_temp"].isna().all()


def test_skip_columns_not_flagged(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    # skip_columns are Control category, not Process — so they are never
    # candidates anyway, but the contract is "whitelisted columns skipped".
    # Verify a constant SCADA *_state_pct column produces zero findings.
    short_policy = _short_policy(policy, min_minutes=2)
    df = tiny_frame_factory(n_rows=20)
    df["granulator_g2_state_pct"] = 50.0  # constant for whole frame
    findings = frozen_sensors.detect(df, short_policy, groups)
    assert [f for f in findings if f.column == "granulator_g2_state_pct"] == []


def test_run_below_min_length_ignored(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    short_policy = _short_policy(policy, min_minutes=10)
    df = tiny_frame_factory(n_rows=8)
    for col in groups.process:
        df[col] = [float(j) for j in range(len(df))]
    # constant 8-sample run is below min 10 → no finding.
    df["granulator_roller_gap"] = 3.0
    findings = frozen_sensors.detect(df, short_policy, groups)
    assert findings == []


def test_epsilon_rate_column_uses_epsilon_equality(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    short_policy = _short_policy(policy, min_minutes=5)
    df = tiny_frame_factory(n_rows=10)
    for col in groups.process:
        df[col] = [float(j) for j in range(len(df))]
    # Within epsilon: tiny variations < 1e-6.
    df["granulator_production_rate"] = [
        5.0 + 1e-10 * j for j in range(len(df))
    ]
    findings = frozen_sensors.detect(df, short_policy, groups)
    rate = [f for f in findings if f.column == "granulator_production_rate"]
    assert len(rate) == 1
