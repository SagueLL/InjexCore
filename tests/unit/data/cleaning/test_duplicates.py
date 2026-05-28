"""Unit tests for ``src.data.cleaning.duplicates``."""
from __future__ import annotations

from typing import Callable

import pandas as pd
import pytest

from src.data.cleaning import duplicates
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=20)
    # Vary one signal column so payload-window check has variation.
    df.loc[:, "granulator_power"] = [float(i) for i in range(len(df))]
    assert duplicates.detect(df, policy, groups) == []


def test_duplicate_timestamp_dropped_keeping_first(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[4, "timestamp"] = df.loc[3, "timestamp"]
    df.loc[:, "granulator_power"] = [float(i) for i in range(len(df))]

    findings = duplicates.detect(df, policy, groups)
    dup_ts = [f for f in findings if f.finding_type == "duplicate_timestamp"]
    assert len(dup_ts) == 1
    assert dup_ts[0].action_taken == "drop_keep_first"
    assert 4 in dup_ts[0].evidence["drop_rows"]

    cleaned = duplicates.apply(df, findings, policy, groups)
    assert len(cleaned) == 9
    assert cleaned["timestamp"].is_unique


def test_duplicate_payload_window_tagged_only(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    # Make signal cols vary except a short identical-payload run at rows 3-4.
    df.loc[:, "granulator_power"] = [float(i) for i in range(len(df))]
    df.loc[4, "granulator_power"] = df.loc[3, "granulator_power"]

    findings = duplicates.detect(df, policy, groups)
    payloads = [f for f in findings if f.finding_type == "duplicate_payload"]
    assert len(payloads) >= 1
    assert payloads[0].severity.value == "aware"
    assert payloads[0].action_taken == "tag_only"


def test_plc_burst_keeps_median_row(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=8, period_s=60.0)
    # Compress rows 2..6 into a 0.5s spaced burst (5 rows ≥ burst_min_rows=3).
    burst_start = df.loc[2, "timestamp"]
    for k in range(5):
        df.loc[2 + k, "timestamp"] = burst_start + pd.Timedelta(milliseconds=500 * k)

    findings = duplicates.detect(df, policy, groups)
    bursts = [f for f in findings if f.finding_type == "plc_burst"]
    assert len(bursts) == 1
    assert bursts[0].count == 5
    kept = bursts[0].evidence["kept_row"]
    dropped = bursts[0].evidence["drop_rows"]
    assert len(dropped) == 4
    assert kept not in dropped

    cleaned = duplicates.apply(df, findings, policy, groups)
    assert len(cleaned) == len(df) - 4


def test_burst_below_min_rows_is_ignored(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=6, period_s=60.0)
    # Only 2 rows within < burst_max_delta_s ⇒ size 2 < burst_min_rows (3).
    df.loc[3, "timestamp"] = df.loc[2, "timestamp"] + pd.Timedelta(milliseconds=500)
    findings = duplicates.detect(df, policy, groups)
    assert [f for f in findings if f.finding_type == "plc_burst"] == []


def test_empty_frame_returns_no_findings(
    empty_frame: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    assert duplicates.detect(empty_frame, policy, groups) == []
