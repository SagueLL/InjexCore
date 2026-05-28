"""Stage 2 — promote ``timestamp`` to the DataFrame index.

A monotonic ``DatetimeIndex`` is a precondition for resampling and for
time-aware rolling windows. Duplicate-on-index rows are dropped (keeping
the first) when ``drop_duplicates_on_index`` is true; this should
normally be a no-op after cleaning.
"""
from __future__ import annotations

import pandas as pd

from src.data.time_series.column_groups import ColumnGroups
from src.data.time_series.policy import TimeSeriesPolicy
from src.data.time_series.reporting import Finding, Severity


def detect(
    df: pd.DataFrame,
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    if not policy.temporal_index.enabled:
        return [
            Finding(
                check="temporal_index",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]
    if isinstance(df.index, pd.DatetimeIndex):
        return [
            Finding(
                check="temporal_index",
                severity=Severity.NORMAL,
                finding_type="already_indexed",
                action_taken="noop",
            )
        ]
    findings: list[Finding] = [
        Finding(
            check="temporal_index",
            severity=Severity.NORMAL,
            finding_type="set_index",
            column="timestamp",
            action_taken="set_index",
        )
    ]
    if policy.temporal_index.drop_duplicates_on_index and "timestamp" in df.columns:
        n_dup = int(df["timestamp"].duplicated().sum())
        if n_dup > 0:
            findings.append(
                Finding(
                    check="temporal_index",
                    severity=Severity.AWARE,
                    finding_type="duplicate_index",
                    column="timestamp",
                    count=n_dup,
                    action_taken="drop_first",
                    evidence={"duplicates": n_dup},
                )
            )
    return findings


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.temporal_index.enabled:
        return df
    if isinstance(df.index, pd.DatetimeIndex):
        return df
    if "timestamp" not in df.columns:
        return df
    out = df.copy()
    if policy.temporal_index.drop_duplicates_on_index:
        out = out.drop_duplicates(subset="timestamp", keep="first")
    out = out.set_index("timestamp").sort_index()
    return out
