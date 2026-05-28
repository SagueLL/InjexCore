"""Stage 3 — optional unification of sensor frequencies.

Disabled by default: cleaning already enforces a ~60 s grid. When
enabled, each column is aggregated using the per-category rule from
``policy.resampling.aggregations`` (``mean`` for sensors, ``last`` for
setpoints, ``max`` for state flags / alarms). Metadata columns fall back
to ``last``.
"""
from __future__ import annotations

import pandas as pd

from src.data.time_series.column_groups import ColumnGroups
from src.data.time_series.policy import ResamplingPolicy, TimeSeriesPolicy
from src.data.time_series.reporting import Finding, Severity


_DEFAULT_AGG = "last"


def _agg_for_column(
    col: str,
    groups: ColumnGroups,
    aggregations: dict[str, str],
) -> str:
    category = groups.semantic_category(col)
    if category is None:
        return _DEFAULT_AGG
    return aggregations.get(category, _DEFAULT_AGG)


def _agg_map(
    df: pd.DataFrame,
    groups: ColumnGroups,
    rs: ResamplingPolicy,
) -> dict[str, str]:
    return {
        col: _agg_for_column(col, groups, rs.aggregations) for col in df.columns
    }


def detect(
    df: pd.DataFrame,
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> list[Finding]:
    if not policy.resampling.enabled:
        return [
            Finding(
                check="resampling",
                severity=Severity.NORMAL,
                finding_type="skipped",
                action_taken="noop",
                evidence={"reason": "disabled"},
            )
        ]
    return [
        Finding(
            check="resampling",
            severity=Severity.AWARE,
            finding_type="resample",
            action_taken=f"resample({policy.resampling.rule})",
            evidence={
                "rule": policy.resampling.rule,
                "rows_before": int(len(df)),
            },
        )
    ]


def apply(
    df: pd.DataFrame,
    findings: list[Finding],
    policy: TimeSeriesPolicy,
    groups: ColumnGroups,
) -> pd.DataFrame:
    if not policy.resampling.enabled:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        # Resampling requires a DatetimeIndex; quietly skip if missing.
        return df
    agg_map = _agg_map(df, groups, policy.resampling)
    return df.resample(policy.resampling.rule).agg(agg_map)
