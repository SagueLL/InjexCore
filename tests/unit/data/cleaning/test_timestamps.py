"""Unit tests for ``src.data.cleaning.timestamps``."""
from __future__ import annotations

from typing import Callable

import pandas as pd
import pytest

from src.data.cleaning import timestamps
from src.data.cleaning.column_groups import ColumnGroups
from src.data.cleaning.policy import CleaningPolicy


def test_golden_path_produces_no_findings(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=20)
    assert timestamps.detect(df, policy, groups) == []


def test_unparseable_timestamp_is_critical_and_dropped(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    df.loc[3, "timestamp"] = pd.NaT
    findings = timestamps.detect(df, policy, groups)

    nat_findings = [f for f in findings if f.finding_type == "unparseable_timestamp"]
    assert len(nat_findings) == 1
    assert nat_findings[0].severity.value == "critical"
    assert nat_findings[0].action_taken == "drop"

    cleaned = timestamps.apply(df, findings, policy, groups)
    assert len(cleaned) == 9
    assert cleaned["timestamp"].notna().all()


def test_non_monotonic_row_is_flagged_and_sorted(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=10)
    # Swap two adjacent timestamps so order goes backwards.
    df.loc[5, "timestamp"] = df.loc[3, "timestamp"]
    findings = timestamps.detect(df, policy, groups)

    nm = [f for f in findings if f.finding_type == "non_monotonic"]
    assert len(nm) == 1
    assert nm[0].severity.value == "critical"

    cleaned = timestamps.apply(df, findings, policy, groups)
    assert cleaned["timestamp"].is_monotonic_increasing


def test_gap_detected_when_delta_exceeds_threshold(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=6, period_s=60.0)
    # Insert a 200-second gap (>2× expected 60s period, <1h max jump).
    df.loc[3:, "timestamp"] = df.loc[3:, "timestamp"] + pd.Timedelta(seconds=200)
    findings = timestamps.detect(df, policy, groups)

    gaps = [f for f in findings if f.finding_type == "gap"]
    assert len(gaps) == 1
    assert gaps[0].severity.value == "important"
    assert gaps[0].action_taken == "tag_only"
    assert gaps[0].evidence["delta_s"] > policy.timestamps.gap_factor * policy.timestamps.expected_period_s


def test_dst_jump_detected_above_max_legal_jump(
    tiny_frame_factory: Callable[..., pd.DataFrame],
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    df = tiny_frame_factory(n_rows=5, period_s=60.0)
    # Push the tail forward by > 1h (max_legal_jump_s = 3600).
    df.loc[2:, "timestamp"] = df.loc[2:, "timestamp"] + pd.Timedelta(hours=2)
    findings = timestamps.detect(df, policy, groups)

    jumps = [f for f in findings if f.finding_type == "dst_jump"]
    assert len(jumps) == 1
    assert jumps[0].severity.value == "important"


def test_empty_frame_returns_no_findings(
    empty_frame: pd.DataFrame,
    policy: CleaningPolicy,
    groups: ColumnGroups,
) -> None:
    assert timestamps.detect(empty_frame, policy, groups) == []
