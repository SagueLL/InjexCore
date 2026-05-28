"""Stage 1 — ensure the timestamp column is ``datetime64[ns]``.

Cleaning already parses ``timestamp`` to datetime, but the cleaned CSV is
re-read as strings by :func:`src.data.time_series.io.load_clean`. This
stage exists so the pipeline is self-sufficient: if the loader did the
parsing already we no-op (a ``NORMAL`` audit finding records that fact);
otherwise we coerce and surface an ``AWARE`` finding.
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
    if not policy.temporal_conversion.enabled:
        return [
            Finding(
                check="temporal_conversion",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]
    col = policy.temporal_conversion.timestamp_col
    if col not in df.columns:
        return [
            Finding(
                check="temporal_conversion",
                severity=Severity.AWARE,
                finding_type="missing_timestamp",
                column=col,
                action_taken="noop",
                evidence={"reason": "column not present"},
            )
        ]
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        return [
            Finding(
                check="temporal_conversion",
                severity=Severity.NORMAL,
                finding_type="already_datetime",
                column=col,
                action_taken="noop",
                evidence={"dtype": str(df[col].dtype)},
            )
        ]
    return [
        Finding(
            check="temporal_conversion",
            severity=Severity.AWARE,
            finding_type="coerce_datetime",
            column=col,
            action_taken="pd.to_datetime",
            evidence={"dtype_before": str(df[col].dtype)},
        )
    ]


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.temporal_conversion.enabled:
        return df
    col = policy.temporal_conversion.timestamp_col
    if col not in df.columns:
        return df
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        return df
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce")
    return out
